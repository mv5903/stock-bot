import asyncio
import datetime
import os
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Optional

import discord
import pandas as pd
from create_dataframe_image import dataframe_to_image
from discord import TextChannel
from discord.ext import commands
from dotenv import dotenv_values, get_key, load_dotenv, set_key
from full_workflow import progress_generator
from paper_trading import get_current_stocks_profit_loss
from top_stock import pick_top_Stock

# Make sure this is the only instance running if attempted to run manually
if len(sys.argv) == 2 and sys.argv[1] == "-s":
    print("Running with systemd")
else:
    result = subprocess.run(["systemctl", "is-active", "bot"], stdout=subprocess.PIPE)
    is_running_already = result.stdout == b"active\n"
    if is_running_already:
        print("Bot is already running in systemd. Please stop it first!")
        exit(1)

# Load environment variables
load_dotenv()
dotenv_path = ".env"
read_only = ["FINNHUB_API_KEY", "DISCORD_BOT_TOKEN"]

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Intents (required to interact with guilds and members)
intents = discord.Intents.all()

# Create a bot instance
bot = commands.Bot(command_prefix="!", intents=intents)

# Sync slash commands to a specific guild (faster updates) or globally (takes up to 1 hour)
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
BOT_CHANNEL_ID = os.getenv("DISCORD_BOT_CHANNEL")

# Used to prohibit simulatenous calls to get_top_stocks_now since the process can take ~ 10 minutes
full_workflow_running = False

# Used for async events
bot_loop = None


@bot.event
async def on_ready():
    """
    Called when the bot is ready to start receiving events, after logging in
    """
    print(f"Logged in as {bot.user}!")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Synced {len(synced)} command(s).")
        global bot_loop
        bot_loop = asyncio.get_event_loop()
    except Exception as e:
        print(f"Failed to sync commands: {e}")


@bot.tree.command(
    name="clear", description="Just like in a CLI ", guild=discord.Object(id=GUILD_ID)
)
async def clear(interaction: discord.Interaction):
    """
    Clears all messages in the channel where the command was invoked
    """
    # Show the user that they need to wait
    await interaction.response.defer()

    # Fetch the channel where the command was invoked
    channel = interaction.channel
    if not channel:
        await interaction.edit_original_response(
            content="Could not determine the channel."
        )
        return

    # Notify that the deletion process is starting
    msg = "Deleting all messages in the channel..."
    await interaction.edit_original_response(content=msg)

    # Delete messages in chunks (Discord API limits batch deletions to 100 messages at a time)
    try:
        deleted_count = 0
        async for message in channel.history(limit=None):
            await message.delete()
            deleted_count += 1

    except Exception as e:
        await interaction.edit_original_response(
            content=f"❌ Failed to delete messages: {str(e)}"
        )


@bot.tree.command(
    name="get_top_stocks_today",
    description="Gets the top stocks today from the overnight job (much faster)",
    guild=discord.Object(id=GUILD_ID),
)
async def get_top_stocks_today(interaction: discord.Interaction):
    """
    Gets the top stocks for the day, using the pre-calculated data from the overnight job
    """
    # Show the user that they need a wait a bit
    await interaction.response.defer()

    msg = "Running Model... [1/1]"
    await interaction.edit_original_response(content=msg)

    top_stocks = pick_top_Stock()

    img_buf = dataframe_to_image(top_stocks, "", money_cols=["current_price"])

    # Create and send the embed
    file = discord.File(img_buf, filename="get_top_stocks_today.png")
    embed = discord.Embed(
        title="**📈 Top Stocks Today**",
        description="Which stocks should you buy today?",
        color=discord.Color.green(),
    )
    embed.set_image(url="attachment://get_top_stocks_today.png")
    await interaction.edit_original_response(embed=embed, attachments=[file])


@bot.tree.command(
    name="get_top_stocks_now",
    description="Gets the top stocks as of right now, running everything (takes a while!)",
    guild=discord.Object(id=GUILD_ID),
)
async def get_top_stocks_now(interaction: discord.Interaction):
    """
    Gets the top stocks for the day, running the full workflow
    """
    global full_workflow_running
    if full_workflow_running:
        await interaction.response.send_message(
            ":no_entry_sign: Process already running!"
        )
        return

    await interaction.response.defer()
    full_workflow_running = True

    # Initialize message and spinner
    msg = "Running full sequence now..."
    spinner = ["|", "/", "-", "\\\\"]
    spinner_index = 0

    # Edit the initial message
    await interaction.edit_original_response(content=msg)

    # Create a task to continuously update the spinner
    async def update_spinner():
        nonlocal msg, spinner_index
        while True:
            # Rotate the spinner
            spinner_index = (spinner_index + 1) % len(spinner)
            spinner_char = spinner[spinner_index]
            await interaction.edit_original_response(
                content=f"**{spinner_char}** {msg}"
            )
            await asyncio.sleep(0.2)  # Adjust spinner speed as needed

    spinner_task = asyncio.create_task(update_spinner())

    try:
        # Process the progress generator
        async for progress in progress_generator():
            # Append progress to the message
            msg = f"{progress}"
    finally:
        # Stop the spinner when progress is complete
        spinner_task.cancel()
        await asyncio.sleep(0.1)  # Allow time for task cleanup

    # Fetch top stocks
    top_stocks = pick_top_Stock()

    img_buf = dataframe_to_image(top_stocks, "", money_cols=["current_price"])

    # Create and send the embed
    file = discord.File(img_buf, filename="get_top_stocks_now.png")
    embed = discord.Embed(
        title="**📈 Top Stocks Now**",
        description="Which stocks should you buy now?",
        color=discord.Color.dark_purple(),
    )
    embed.set_image(url="attachment://get_top_stocks_now.png")
    full_workflow_running = False
    await interaction.edit_original_response(embed=embed, attachments=[file])


@bot.tree.command(
    name="list_env_variables",
    description="Lists all variables from .env file",
    guild=discord.Object(id=GUILD_ID),
)
async def list_env_variables(interaction: discord.Interaction):
    """
    Lists all environment variables from the .env file
    """
    env_vars = dotenv_values(dotenv_path=dotenv_path)

    embed = discord.Embed(
        title="Current Environment Variables",
        color=discord.Color.purple(),
    )

    protected_vars = {key: value for key, value in env_vars.items() if key in read_only}
    unprotected_vars = {
        key: value for key, value in env_vars.items() if key not in read_only
    }

    # Group readonly and editable into 2 groups
    # Add protected variables as a field
    if protected_vars:
        embed.add_field(
            name="🔒 Protected Variables (Read Only)",
            value="\n".join(
                [f"**{key}**: {value}" for key, value in protected_vars.items()]
            )
            or "None",
            inline=False,
        )

    # Add unprotected variables as a field
    if unprotected_vars:
        embed.add_field(
            name="🔓 Unprotected Variables (Mutable)",
            value="\n".join(
                [f"**{key}**: {value}" for key, value in unprotected_vars.items()]
            )
            or "None",
            inline=False,
        )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="set_env_variable",
    description="Sets a variable from .env file (see /list_env_variables)",
    guild=discord.Object(id=GUILD_ID),
)
async def set_env_variable(interaction: discord.Interaction, key: str, new_value: str):
    """
    Sets a variable from the .env file
    """
    env_vars = dotenv_values(dotenv_path=dotenv_path)

    # Make sure key exists
    if key not in env_vars:
        await interaction.response.send_message(
            content=f"The env variable **{key}** does not exist."
        )
        return

    # Make sure key isn't protected or sensitive
    if key in read_only:
        await interaction.response.send_message(
            content=f"The env variable **{key}** is protected and shouldn't be changed at all. Please edit the .env directly on the server if you really need to change it. Current protected environment variables: **{str(read_only)}**."
        )
        return

    set_key(dotenv_path=dotenv_path, key_to_set=key, value_to_set=new_value)
    subprocess.run(["chmod", "777", ".env"])

    await interaction.response.send_message(
        content=f"Environment variable **{key}** set to **{new_value}** successfully."
    )


@bot.tree.command(
    name="get_paper_portfolio",
    description="Gets the current paper trading portfolio with live data",
    guild=discord.Object(id=GUILD_ID),
)
async def get_paper_portfolio(interaction: discord.Interaction, tickers: Optional[str]):
    """
    Gets the current paper trading portfolio with live data
    """
    await interaction.response.defer()
    tickers = tickers.split(",") if tickers is not None else ""
    list_specific_only = tickers != "" and len(tickers) > 0
    df = get_current_stocks_profit_loss(tickers)

    if list_specific_only:
        df = df[
            [
                "stock_symbol",
                "quantity",
                "price",
                "trade_date",
                "current_price",
                "total_gain_loss",
            ]
        ]
    else:
        df = df[["stock_symbol", "current_price", "total_gain_loss"]]

    # Generate the image
    img_buf = dataframe_to_image(
        df, "total_gain_loss", money_cols=["current_price", "total_gain_loss"]
    )

    # Add summary stats
    gain_loss_sum = df["total_gain_loss"].sum()
    total_movement = df["current_price"].sum()
    gain_loss_str = f"\n**Total Gain/Loss: `${gain_loss_sum:.2f}`**\n**Total Price: `${total_movement:.2f}`**"

    # Create and send the embed
    file = discord.File(img_buf, filename="portfolio_table.png")
    embed = discord.Embed(
        title="📈 Current Paper Trading Portfolio",
        description=gain_loss_str,
        color=discord.Color.blue(),
    )
    embed.set_image(url="attachment://portfolio_table.png")
    await interaction.edit_original_response(embed=embed, attachments=[file])


# Cron Watching
stop_event = threading.Event()


async def send_nightly_embed(bot_channel: TextChannel):
    """
    Sends the nightly embed with the top stocks, as activated by the nightly cron job
    """
    today_str = datetime.datetime.now().strftime("%x")
    top_n = os.getenv("TOP_N_STOCKS")
    top_stocks = pick_top_Stock()

    img_buf = dataframe_to_image(top_stocks, "", money_cols=["current_price"])

    # Create and send the embed
    file = discord.File(img_buf, filename="send_nightly_embed.png")
    embed = discord.Embed(
        title=f"**:full_moon_with_face: {today_str} Nightly Run Results: Top {top_n} Stocks**\n",
        description="Which stocks should you buy today?",
        color=discord.Color.dark_grey(),
    )
    embed.set_image(url="attachment://send_nightly_embed.png")
    await bot_channel.send(embed=embed, file=file)


async def send_paper_buy_embed(bot_channel: TextChannel):
    """
    Sends the paper buy embed with the stocks that were just purchased, as activated by the paper buy cron job every Monday
    """
    # SELECT stock_symbol, quantity, price FROM paper_trades
    db_path = os.getenv("DB_PATH")
    conn = sqlite3.connect(db_path)

    # Load tech_stocks that have valuation data
    df_stocks = pd.read_sql_query(
        "SELECT stock_symbol, quantity, price FROM paper_trades", conn
    )

    today_str = datetime.datetime.now().strftime("%x")
    total_cost = df_stocks["price"].sum()

    conn.close()

    img_buf = dataframe_to_image(df_stocks, "", money_cols=["price"])

    # Create and send the embed
    file = discord.File(img_buf, filename="send_paper_buy_embed.png")
    embed = discord.Embed(
        title=f":moneybag: Week of {today_str} stocks were just purchased, totalling **${total_cost:.2f}**: \n",
        color=discord.Color.orange(),
    )
    embed.set_image(url="attachment://send_paper_buy_embed.png")
    await bot_channel.send(embed=embed, file=file)


async def send_paper_sell_embed(bot_channel: TextChannel):
    """
    Sends the paper sell embed with the stocks that were just sold, as activated by the paper sell cron job every Sunday
    """
    db_path = os.getenv("DB_PATH")
    conn = sqlite3.connect(db_path)

    # Use the current date to find the stocks with the current date falling between their week_start_date and week_end_date
    current_date = datetime.datetime.now().date()
    df_stocks = pd.read_sql_query(
        f"SELECT * FROM portfolio WHERE week_end_date >= '{current_date}' AND week_start_date <= '{current_date}' LIMIT 10",
        conn,
    )

    # From query, calculate total cost of the week and total gain/loss
    total_cost = df_stocks["total_cost"].sum()
    total_gain_loss = df_stocks["weekly_profit_loss"].sum()
    days_since_monday = datetime.datetime.now().weekday()  # 0 for Monday, 6 for Sunday
    start_day = datetime.datetime.now() - datetime.timedelta(days=days_since_monday)

    conn.close()

    df_stocks = df_stocks[
        [
            "stock_symbol",
            "total_quantity",
            "total_cost",
            "weekly_profit_loss",
        ]
    ]

    img_buf = dataframe_to_image(
        df_stocks,
        "weekly_profit_loss",
        money_cols=["total_cost", "weekly_profit_loss"],
    )

    # Create and send the embed
    file = discord.File(img_buf, filename="send_paper_sell_embed.png")
    embed = discord.Embed(
        title=f":convenience_store: Week of {start_day.date()} Sell Results:",
        description=f"Total Cost: **${total_cost:.2f}**\nTotal Gain/Loss: **${total_gain_loss:.2f}**",
        color=discord.Color.red(),
    )
    embed.set_image(url="attachment://send_paper_sell_embed.png")
    await bot_channel.send(embed=embed, file=file)


def cron_watch(e):
    """
    Watches for changes in the cron environment file and sends the appropriate embeds. A separate thread is used to run this function.
    When the particular cron job is activated, the corresponding flag is set to `1` in the `.env.cron` file by the cron job's script.
    Then, once the flag is detected, the corresponding embed is sent and the flag is reset to `0`.
    """
    cron_env_path = "../cronlogs/.env.cron"
    while not stop_event.is_set():
        time.sleep(5)
        bot_channel = bot.get_channel(int(BOT_CHANNEL_ID))
        if bot_channel is None:
            print("Incorrect BOT CHANNEL provided: ", bot, bot_channel, BOT_CHANNEL_ID)
            continue

        if bot_loop is None:
            continue

        nightly = get_key(cron_env_path, "NIGHTLY")
        paper_buy = get_key(cron_env_path, "PAPER_BUY")
        paper_sell = get_key(cron_env_path, "PAPER_SELL")

        if nightly is not None and nightly == "1":
            future = asyncio.run_coroutine_threadsafe(
                send_nightly_embed(bot_channel), bot_loop
            )
            try:
                future.result()  # This will raise any exception that occurred in the coroutine
            except Exception as e:
                print("Exception from send_nightly_embed:", e)
            set_key(cron_env_path, "NIGHTLY", "0")
            subprocess.run(["chmod", "777", cron_env_path])

        elif paper_buy is not None and paper_buy == "1":
            future = asyncio.run_coroutine_threadsafe(
                send_paper_buy_embed(bot_channel), bot_loop
            )
            try:
                future.result()  # This will raise any exception that occurred in the coroutine
            except Exception as e:
                print("Exception from send_paper_buy_embed:", e)
            set_key(cron_env_path, "PAPER_BUY", "0")
            subprocess.run(["chmod", "777", cron_env_path])

        elif paper_sell is not None and paper_sell == "1":
            future = asyncio.run_coroutine_threadsafe(
                send_paper_sell_embed(bot_channel), bot_loop
            )
            try:
                future.result()  # This will raise any exception that occurred in the coroutine
            except Exception as e:
                print("Exception from send_paper_sell_embed:", e)

            set_key(cron_env_path, "PAPER_SELL", "0")
            subprocess.run(["chmod", "777", cron_env_path])


watch_thread = threading.Thread(target=cron_watch, args=(stop_event,))
watch_thread.start()


# Run the bot
bot.run(TOKEN)
