from consumer import CoinConsumer


def run_services():
    producer = CoinConsumer()
    producer.run()


run_services()
