import logging
import os
import urllib.parse
from logging import Logger

import boto3
from pyspark.sql import DataFrame
from pyspark.sql.functions import col


def get_bucket_from_url(url):
    return urllib.parse.urlparse(url, allow_fragments=False).netloc


def get_ssm_param(ssm_client, name):
    return ssm_client.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


# change datatype of `date` type column into `timestamp`
def change_dtype(df: DataFrame):
    for name, dtype in df.dtypes:
        if dtype == "date":
            df = df.withColumn(name, col(name).cast("timestamp"))
    return df


def unload_to_snowflake(df, sf_options, table):
    logging.info(f"Loading {table} table to Snowflake")
    (
        df.write.format("net.snowflake.spark.snowflake")
        .options(**sf_options)
        .option("dbtable", table)
        .option("truncate_table", "on")
        .option("usestagingtable", "off")
        .mode("overwrite")
        .save()
    )
    logging.info(f"{table} Snowflake table has been loaded successfully")


def configure_logging(logger: Logger):
    logger.setLevel(os.environ.get("LOGLEVEL", "INFO"))
    handler = logging.StreamHandler()
    bf = logging.Formatter("[{asctime}:{funcName}:{levelname:8s}] {message}", style="{")
    handler.setFormatter(bf)
    logger.addHandler(handler)


def date_to_str(date, format="long"):
    return date.strftime("%Y-%m-%d") if format == "short" else date.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-4]


def is_s3_folder_empty(bucket, key, aws_region):
    s3 = boto3.resource("s3", region_name=aws_region)
    bucket = s3.Bucket(bucket)
    objs = list(bucket.objects.filter(Prefix=key))
    return not len(objs) >= 1
