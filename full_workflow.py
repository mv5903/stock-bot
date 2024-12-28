import asyncio
import datetime

from dotenv import set_key


async def stream_subprocess(cmd_list, cwd=None):
    """
    Spawns a subprocess (non-blocking) and yields each line of stdout as it's produced.
    """
    # Create the subprocess
    proc = await asyncio.create_subprocess_exec(
        *cmd_list,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    # Read line-by-line (async) until process terminates
    while True:
        if proc.stdout is None:
            break

        line = await proc.stdout.readline()
        if not line:
            break

        # Yield the decoded line
        yield line.decode("utf-8").rstrip()

    # Wait for the process to exit completely
    await proc.wait()


async def progress_generator():
    """
    Orchestrates the full workflow, yielding progress updates as each step completes.
    To consume, simply iterate over the generator like so:
    ```
    async for progress in progress_generator():
        print(progress) # Do something with the progress update
    ```
    """
    yield "Step 1/4: Finding stocks"
    # Run the script, streaming the output
    async for line in stream_subprocess(
        ["/stocks/stock-bot/venv/bin/python3", "-u", "tech_stock_list_dl.py"]
    ):
        yield f"    [Step 1/4 - Finding Stocks]: {line}"

    yield "Step 2/4: Running stock evaluation"
    async for line in stream_subprocess(
        ["/stocks/stock-bot/venv/bin/python3", "-u", "stock_valuation.py"]
    ):
        yield f"    [Step 2/4 - Stock Valuation]: {line}"

    yield "Step 3/4: Finding news articles"
    async for line in stream_subprocess(
        ["/stocks/stock-bot/venv/bin/python3", "-u", "find_articles.py"]
    ):
        yield f"    [Step 3/4 - Find Articles]: {line}"

    yield "Step 4/4: Scraping & analyzing articles"
    async for line in stream_subprocess(
        ["/stocks/stock-bot/venv/bin/scrapy", "crawl", "db_spider"],
        cwd="/stocks/stock-bot/sentiment_scraper",
    ):
        yield f"    [Step 4/4 - Scraping]: {line}"

    yield "Done!"


async def main():
    async for _ in progress_generator():
        pass


# Activated from the nightly cron job
if __name__ == "__main__":
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{now_str}: Nightly Run Started")
    asyncio.run(main())
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{now_str}: Nightly Run Completed")
    set_key("../cronlogs/.env.cron", "NIGHTLY", "1")
