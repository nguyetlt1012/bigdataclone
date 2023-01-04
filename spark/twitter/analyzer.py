import os
import logging
import time
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.functions import date_trunc, from_unixtime, col, udf, count, sum, lit
from pyspark.sql.types import IntegerType
from hdfs import InsecureClient
from logging.handlers import RotatingFileHandler

# Add your own conf dir
os.environ['HADOOP_CONF_DIR'] = os.path.abspath(os.getcwd()) + '/spark/conf'
os.environ['YARN_CONF_DIR'] = os.path.abspath(os.getcwd()) + '/spark/conf'

positive = [
    "upgrade",
    "upgraded",
    "long",
    "buy",
    "buying",
    "growth",
    "good",
    "gained",
    "well",
    "great",
    "nice",
    "top",
    "support",
    "update",
    "strong",
    "bullish",
    "bull",
    "highs",
    "win",
    "positive",
    "profits",
    "bonus",
    "potential",
    "success",
    "winner",
    "winning",
    "good"]

negative = [
    "downgraded",
    "bears",
    "bear",
    "bearish",
    "drop",
    "volatile",
    "short",
    "sell",
    "selling",
    "forget",
    "down",
    "resistance",
    "sold",
    "sellers",
    "negative",
    "selling",
    "blowout",
    "losses",
    "war",
    "lost",
    "loser"]


class TwitterDataTransformer():
    def __init__(self):
        # Should consider using new image for nodemanager if want to use spark yarn
        # currently mismatching python ver if using udf
        self.spark = SparkSession.builder\
            .config("spark.app.name", "TwitterDataAnalyzer")\
            .config("spark.master", "local[*]")\
            .config("spark.jars.packages", "com.datastax.spark:spark-cassandra-connector_2.12:3.2.0")\
            .config("spark.sql.extensions", "com.datastax.spark.connector.CassandraSparkExtensions")\
            .config("spark.cassandra.connection.host", "172.20.0.15")\
            .config("spark.driver.host", "127.0.0.1")\
            .config("spark.cassandra.auth.username", "cassandra")\
            .config("spark.cassandra.auth.password", "cassandra")\
            .getOrCreate()
        # Options if my computer is better...
        #  .config("spark.driver.memory", "2g")\
        #  .config("spark.executor.memory", "2g")\
        #  .config("spark.executor.instances", "2")\
        self.frequency = ['minute', 'hour', 'day', 'week', 'month', 'year']

    def map_time(self, df, frequency):
        return df.withColumn('Recorded time', date_trunc(
            frequency, from_unixtime(col('Recorded time'))))

    def analyze_statistics(self, df, frequency):
        def get_sentiment(tweet_content):
            for word in positive:
                if tweet_content.find(word) != -1:
                    return 1
            for word in negative:
                if tweet_content.find(word) != -1:
                    return -1
            return 0

        get_sentiment_udf = udf(lambda content: get_sentiment(content), IntegerType())
        df = df.withColumn('sentiment', get_sentiment_udf(col('Tweet')))
        df = df.groupBy('Symbol', 'Recorded time')\
               .agg(count('Tweet').alias('count'),
                    sum('sentiment').alias('sentiment'))

        df = df.select(col('Symbol').alias('symbol'),
                       col('Recorded time').alias('recorded_time'),
                       col('count'), lit(frequency).alias('frequency'), col('sentiment'))
        return df

    def transform_data(self, files):
        df = self.spark.read.format('csv')\
            .option('mode', 'DROPMALFORMED')\
            .option('header', True)\
            .option('inferSchema', True)\
            .load(files)
        frequency_dfs = {f: self.map_time(df, f) for f in self.frequency}
        frequency_dfs = {f: self.analyze_statistics(df, f) for f, df in frequency_dfs.items()}
        # This only work because I'm in a hurry. If database too big it will explode
        result_df = self.spark.read.format('org.apache.spark.sql.cassandra')\
            .options(table='tweet_trending', keyspace='coinhub')\
            .load()
        for frequency_df in frequency_dfs.values():
            result_df = result_df.union(frequency_df)\
                .groupBy('symbol', 'recorded_time', 'frequency')\
                .agg(sum('count').alias('count'),
                     sum('sentiment').alias('sentiment'))
            # Cassandra requires cols in alphabet order
            result_df = result_df.select(['symbol', 'recorded_time', *sorted(result_df.columns[2:])])
        return result_df


class TwitterDataAnalyzer():
    def __init__(self, current_date, latest_file_time=None):
        log_handler = RotatingFileHandler(
            f"{os.path.abspath(os.getcwd())}/spark/twitter/logs/analyzer.log",
            maxBytes=104857600, backupCount=10)
        logging.basicConfig(
            format='%(asctime)s,%(msecs)d <%(name)s>[%(levelname)s]: %(message)s',
            datefmt='%H:%M:%S',
            level=logging.DEBUG,
            handlers=[log_handler])
        self.logger = logging.getLogger('twitter_analyzer')
        self.transformer = TwitterDataTransformer()
        self.hdfs_client = InsecureClient('http://localhost:9870', user='root')
        self.current_date = datetime(*[int(v) for v in current_date.split('/')]).timestamp()
        self.latest_file_time = latest_file_time

    def transform_and_save_data(self, files):
        self.logger.info('Start transforming data')
        frequency_df = self.transformer.transform_data(files)
        frequency_df.write.format('org.apache.spark.sql.cassandra')\
                    .mode('append')\
                    .options(table='tweet_trending', keyspace='coinhub')\
                    .save()

    def get_hdfs_new_files(self, date_to_get, latest_file_time=None):
        self.logger.info('Get files from hdfs')
        str_current_date = datetime.fromtimestamp(date_to_get).strftime('%Y/%-m/%-d')
        file_dir = '/twitterData/' + str_current_date
        hdfs_files = self.hdfs_client.list(file_dir)

        if latest_file_time:
            self.logger.info('Latest file pull is on '
                             + datetime.fromtimestamp(float(latest_file_time))
                                       .strftime('%Y/%-m/%-d %H:%M:%S'))
            hdfs_files = filter(lambda f: f.split('.')[1] > latest_file_time, hdfs_files)
        return list(map(lambda f: file_dir + '/' + f, hdfs_files))

    def analyze_data(self, analyzing_date, latest_file_time, save_latest_file_time=True):
        self.logger.info('Start analyzing for date '
                         + datetime.fromtimestamp(analyzing_date).strftime('%Y/%-m/%-d'))
        new_files = self.get_hdfs_new_files(analyzing_date, latest_file_time)

        if new_files:
            self.transform_and_save_data(new_files)
            if save_latest_file_time:
                self.latest_file_time = new_files[-1].split('.')[1]

    def run(self):
        self.logger.info('Start analyzing twitter data from hdfs')
        error_cnt = 0
        while True:
            today = datetime.now().timestamp()

            try:
                # Analyze if any remaining files in yesterday
                if today - self.current_date < 86400 and self.latest_file_time:
                    self.analyze_data(
                        self.current_date - 86400, self.latest_file_time)
                self.analyze_data(self.current_date, self.latest_file_time)
            except Exception as e:
                self.logger.error(f"An error happened while analyzing {e}")
                error_cnt += 1
                if error_cnt == 10:
                    self.logger.info('More than 10 errors happened. Shutdown the service')
                    raise RuntimeError("Force shutdown")

            if today - self.current_date < 86400:
                self.logger.info("Sleeping for 3 hours")
                time.sleep(10800)
            else:
                self.current_date += 86400
