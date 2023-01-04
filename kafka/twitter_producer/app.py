from producer import TwitterProducer
import os

with open(f"{os.path.abspath(os.getcwd())}/kafka/twitter_producer/secret", "r") as file:
    bearer_token = file.readline().split(' ')[2].split('\n')[0]


def run_service():
    producer = TwitterProducer(bearer_token=bearer_token, return_type=dict)
    producer.run()


run_service()
