import datetime
import subprocess
import asyncio
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
        stderr=asyncio.subprocess.STDOUT
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
    yield "Step 1: Finding stocks"
    # Run the script, streaming the output
    async for line in stream_subprocess(["/stocks/stock-bot/venv/bin/python3", "-u", "tech_stock_list_dl.py"]):
        yield f"    [Step 1]: {line}" 

    yield "Step 2: Running stock evaluation"
    async for line in stream_subprocess(["/stocks/stock-bot/venv/bin/python3", "-u", "stock_valuation.py"]):
        yield f"    [Step 2]: {line}"

    yield "Step 3: Finding news articles"
    async for line in stream_subprocess(["/stocks/stock-bot/venv/bin/python3", "-u", "find_articles.py"]):
        yield f"    [Step 3]: {line}"

    yield "Step 4: Scraping & analyzing articles"
    async for line in stream_subprocess(["/stocks/stock-bot/venv/bin/scrapy", "crawl", "db_spider"], cwd="/stocks/stock-bot/sentiment_scraper"):
        yield f"    [Step 4]: {line}"
    
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


