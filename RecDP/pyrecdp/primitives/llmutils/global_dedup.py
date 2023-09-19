import argparse
import os, sys
from pyrecdp.core.utils import Timer
from pyrecdp.primitives.llmutils.utils import get_target_file_list, read_json, read_parquet
from pyrecdp.primitives.llmutils import global_hash, global_hash_spk, index_based_reduction, index_based_reduction_spk
import pyspark.sql.functions as F
from pyrecdp.core import SparkDataProcessor

def pre_check(spark_df):
    column_names = spark_df.columns
    step_list = [
        ['text'],
        ['hash', 'doc_id', 'source'],
        ['hash_count', 'doc_id_list', 'source_list'],
        ['hash', 'doc_id']
    ]
    for idx in [1, 2, 3, 0]:
        match = True
        for key in step_list[idx]:
            if key not in column_names:
                match = False
                break
        if match:
            return idx + 1
    return 0

def combine_hash_indexing_spk(spark_df):
    from pyspark.sql.types import ArrayType, StringType
    dict_df_all = spark_df
    def union_set(set_list):
        """  set_list is a list of set """
        return [x for set_x in set_list for x in set_x]
            
    union_set_udf = F.udf(union_set, ArrayType(StringType()))
    dict_df_all = dict_df_all.groupby('hash').agg(union_set_udf(F.collect_list("doc_id_list")).alias('doc_id_list'), union_set_udf(F.collect_list("source_list")).alias('source_list'), F.sum("hash_count").alias('hash_count'))
    return dict_df_all

def get_hash_indexing_spk(spark_df):
    dict_df_all = spark_df
    dict_df_all = dict_df_all.groupby('hash').agg(F.collect_list("doc_id").alias('doc_id_list'), F.collect_list("source").alias('source_list'), F.count("hash").alias('hash_count'))
    return dict_df_all

def get_duplication_list_spk(spark_df):
    dict_df_all = spark_df  
    dict_df_all = dict_df_all.filter("hash_count > 1").cache()
    dict_df_all = dict_df_all.withColumn("doc_id_list", F.slice(F.col("doc_id_list"), 2, F.size(F.col("doc_id_list"))))\
                             .withColumn("doc_id_list", F.explode("doc_id_list"))\
                             .select(F.col("hash"), F.col("doc_id_list").alias("doc_id"))                         
    return dict_df_all

def combine_hash_indexing(data_dir_list, out_dir, spark = None):
    if spark == None:
        rdp = SparkDataProcessor()
        spark=rdp.spark
    first = True
    for data_dir in data_dir_list:
        df = spark.read.option("recursiveFileLookup", "true").parquet(data_dir)
        if first:
            dict_df_all = df
            first = False
        else:
            dict_df_all = dict_df_all.union(df)
    total_docs = dict_df_all.count()
    
    index_df = combine_hash_indexing_spk(dict_df_all)
    hash_total_docs = index_df.count()
    
    index_df.write.mode('overwrite').parquet(f"{out_dir}")
    print(f"Index has been written to {out_dir}")
    print(f"  Total hash count from different source is {total_docs}")
    print(f"  Total distinct hash count is {hash_total_docs}")
    
def get_hash_indexing(data_dir, out_dir, spark = None):
    if spark == None:
        rdp = SparkDataProcessor()
        spark=rdp.spark
    dict_df_all = spark.read.option("recursiveFileLookup", "true").parquet(data_dir)
    total_docs = dict_df_all.count()
    
    index_df = get_hash_indexing_spk(dict_df_all)
    hash_total_docs = index_df.count()
    
    index_df.write.mode('overwrite').parquet(f"{out_dir}")
    print(f"Index has been written to {out_dir}")
    print(f"  Total processed documents count is {total_docs}")
    print(f"  Total distinct hash count is {hash_total_docs}")

def get_duplication_list(data_dir, out_dir, spark = None):
    if spark == None:
        rdp = SparkDataProcessor()
        spark=rdp.spark
    dict_df_all = spark.read.option("recursiveFileLookup", "true").parquet(data_dir)
    duplicate_df = get_duplication_list_spk(dict_df_all)
    duplicate_df.write.mode("overwrite").parquet(f"{out_dir}")


def global_dedup(data_dir, out_dir, source, in_type = 'parquet', is_norm = True, dup_dir = None):
    data_files = get_target_file_list(data_dir, in_type)
    data_files = [os.path.join(data_dir, f) for f in data_files]
    rdp = SparkDataProcessor()
    spark=rdp.spark
    hash_df, dup_df = None, None
    
    if in_type == 'parquet':
        spark_df = read_parquet(data_files, spark)
    elif in_type == 'jsonl':
        spark_df = read_json(data_files, spark)
    
    start_step = pre_check(spark_df)
    
    # 1. if input hasn't been processed by global hash
    if start_step <= 1:
        with Timer(f"Generate Global Hash, normailization is {is_norm}"):
            spark_df = global_hash_spk(spark_df, source, is_norm).cache()
            hash_df = spark_df
            post_global_hash_count = spark_df.count()

    # 2. get global hash indexing
    if start_step <= 2:
        with Timer(f"Generate Global indexing based on hash"):
            spark_df = get_hash_indexing_spk(spark_df).cache()
            index_count = spark_df.count()

    # 3. generate duplication indexing
    if start_step <= 3:
        with Timer(f"Generate global duplication list"):
            dup_df = get_duplication_list_spk(spark_df).cache()
            duplication_count = dup_df.count()
    
    # 4. deduplicate input
    if start_step <= 4:
        if hash_df != None and dup_df != None:
            pass
        elif hash_df == None and dup_df == None and dup_dir != None:
            hash_df = spark_df
            dup_df = read_parquet(dup_dir, spark)
        elif dup_dir == None:
            raise ValueError("Global Dedup unable to proceed because no duplication dict is provided.")

        with Timer(f"reduce input file based on detected duplication"):
            out_df = index_based_reduction_spk(hash_df, dup_df, True).cache()
            post_global_dedup_count = out_df.count()
            
    out_file = os.path.join(out_dir, 'deduplicated')
    out_df.write.mode("overwrite").parquet(f"{out_file}")
            
    print(f"Input data count is {post_global_hash_count}")
    print(f"  unique data count is {index_count}")
    print(f"  duplication count is {duplication_count}")
    print(f"  post-deduplication count is {post_global_dedup_count}")
        
    
def global_dedup_spk(spark_df, source, is_norm):
    spark = spark_df.sparkSession
    # 1. if input hasn't been processed by global hash
    with Timer(f"Generate Global Hash, normailization is {is_norm}"):
        hash_df = global_hash_spk(spark_df, source, is_norm).cache()
        post_global_hash_count = hash_df.count()
    
    # 2. get global hash indexing
    with Timer(f"Generate Global indexing based on hash"):
        ret_df = get_hash_indexing_spk(hash_df).cache()
        index_count = ret_df.count()

    # 3. generate duplication indexing
    with Timer(f"Generate global duplication list"):
        ret_df = get_duplication_list_spk(ret_df).cache()
        duplication_count = ret_df.count()
    
    # 4. deduplicate input
    with Timer(f"reduce input file based on detected duplication"):
        out_df = index_based_reduction_spk(hash_df, ret_df, True).cache()
        post_global_dedup_count = out_df.count()
        
    print(f"Input data count is {post_global_hash_count}")
    print(f"  unique data count is {index_count}")
    print(f"  duplication count is {duplication_count}")
    print(f"  post-deduplication count is {post_global_dedup_count}")
        
    return out_df