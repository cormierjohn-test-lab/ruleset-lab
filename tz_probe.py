# Databricks notebook source
from datetime import datetime

# COMMAND ----------

# DEFECT A: naive datetime.now() with no timezone
run_started = datetime.now()

# COMMAND ----------

orders_df = spark.sql("""
    SELECT
        STORE_NUMBER,
        ORDER_TOTAL,
        CURRENT_DATE() AS BUSINESS_DATE
    FROM commondata.shared.ORDERS_TBL
""")

# COMMAND ----------

orders_df.write.mode("overwrite").saveAsTable("commondata.shared.ORDERS_DAILY_TBL")
print(f"Run started {run_started}")
