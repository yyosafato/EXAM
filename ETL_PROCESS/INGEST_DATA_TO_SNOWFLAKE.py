import logging
import sys
import time as time_
from datetime import date

import boto3
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession

from mdp_synergi_upstream.common.utils import configure_logging, get_ssm_param


logger = logging.getLogger(__name__)
configure_logging(logger)

metrics = {"execution_time_ms": 0, "tables_loaded": 0}


def millis():
    return int(round(time_.time() * 1000))


def read_table(url, table, username, password):

    spark = SparkSession.builder.appName("INGEST SYNERGI").getOrCreate()
    df = (
        spark.read.format("jdbc")
        .option("url", url)
        .option("dbtable", f"ENERGY.{table}")
        .option("user", username)
        .option("password", password)
        .load()
    )

    return df


def main():
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "aws_region",
            "output_bucket",
            "sqlserver_user",
            "sqlserver_password",
            "sqlserver_url",
            "sqlserver_tables",
            "sf_user",
            "sf_passwd",
            "sf_url",
            "sf_db",
            "sf_schema",
            "sf_warehouse",
        ],
    )

    aws_region = args["aws_region"]
    output_bucket = args["output_bucket"]
    logger.info(f"Input vars: aws region - {aws_region}, output bucket - {output_bucket}")

    ssm = boto3.client("ssm", region_name=aws_region)

    sqlserver_creds = {
        "sqlserver_user": get_ssm_param(ssm, args["sqlserver_user"]),
        "sqlserver_password": get_ssm_param(ssm, args["sqlserver_password"]),
        "sqlserver_url": get_ssm_param(ssm, args["sqlserver_url"]),
    }

    sf_options = {
        "sfURL": get_ssm_param(ssm, args["sf_url"]),
        "sfUser": get_ssm_param(ssm, args["sf_user"]),
        "sfPassword": get_ssm_param(ssm, args["sf_passwd"]),
        "sfDatabase": args["sf_db"],
        "sfSchema": args["sf_schema"],
        "sfWarehouse": args["sf_warehouse"],
    }

    table_list = args["sqlserver_tables"].split(",")

    for table in table_list:
        df = read_table(
            sqlserver_creds["sqlserver_url"],
            table,
            sqlserver_creds["sqlserver_user"],
            sqlserver_creds["sqlserver_password"],
        )
        today = date.today().strftime("%Y-%m-%d")
        logger.info(f"Uploading table to S3: {table} for date {today}")
        df.write.mode("overwrite").parquet(f"{output_bucket}/parquet/Synergy/{table}/{today}")
        write_to_snowflake(df, sf_options, table)

    logger.info(f"Job {args['JOB_NAME']} succeeded")


def write_to_snowflake(df, sf_options, table):
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


if __name__ == "__main__":
    main()
