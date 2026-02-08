import schedule
import time
from ingester import load_config, poll_and_update

config = load_config()

def job():
    poll_and_update(config)

schedule.every(config['sources']['sharepoint']['poll_interval_min']).minutes.do(job)
schedule.every(config['sources']['confluence']['poll_interval_min']).minutes.do(job)

while True:
    schedule.run_pending()
    time.sleep(60)