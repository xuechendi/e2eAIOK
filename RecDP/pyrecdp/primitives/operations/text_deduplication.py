from .base import BaseLLMOperation, LLMOPERATORS
from ray.data import Dataset
from pyspark.sql import DataFrame
import os
from pyrecdp.core.cache_utils import RECDP_MODELS_CACHE

import argparse
import os
import sys

import re
from nltk import ngrams
import pyspark.sql.functions as F
from pyrecdp.core.utils import Timer
from pyspark.sql import Row

NON_ALPHA = re.compile("[^A-Za-z_0-9]")
THRESHOLD = 200

from pyrecdp.primitives.llmutils.third_party import generate_connected_components, generate_duplicates_dict
from datasketch import MinHash
from pyspark.sql.types import StringType, IntegerType
import hashlib

import ftfy, re, string

def normalize_str(s):
    if s:
        s = ftfy.fix_text(s, normalization="NFC")
    else:
        s = ""
    return s

def clean_str(s):
    s = normalize_str(s)
    s = s.lower().translate(str.maketrans("", "", string.punctuation))
    s = re.sub(r"\s+", " ", s.strip())
    return s

def global_unique_id(df, col_name):
    ret_df = df
    if 'filename_docid' in df.schema.names:
        ret_df = ret_df.withColumn(col_name, F.regexp_replace(F.col("filename_docid"), "/", "_"))
        return ret_df
    if col_name in df.schema.names:
        return ret_df
    ret_df = ret_df.select(F.concat_ws("@", F.lit("global_id"), F.monotonically_increasing_id()).alias(col_name), "*")
    return ret_df

def generate_hash_values(content, idx, num_perm, ngram_size, hashranges, permutations, is_norm):
    # 0. apply normalization to content
    if is_norm:
        content = clean_str(content)    
    tokens = {" ".join(t) for t in ngrams(NON_ALPHA.split(content), ngram_size)}
    
    #1. using bigcode impl to calculate minHash
    m = MinHash(num_perm=num_perm, permutations = permutations )
    m.update_batch([token.encode('utf8') for token in tokens])
    
    #2. map results to each band
    Hs = [bytes(m.hashvalues[start:end].byteswap().data) for start, end in hashranges]
    return [(band_idx, H, idx) for band_idx, H in enumerate(Hs)]

def generate_edges(nodes):
    if len(nodes) <= 1:
        return []

    min_node = min(nodes)
    return [(n, min_node) for n in nodes if n != min_node]

def get_hash_ranges(B = None, R = None):
    HASH_RANGES = [(i * R, (i + 1) * R) for i in range(B)]
    return HASH_RANGES

def convert_to_slimPJ_fmt(first, second):
    return [f"{first} :: {second}"]

def minHashLSH_prepare(df, num_perm, ngram_size, B, R, is_norm):
    HASH_RANGES = get_hash_ranges(B, R)
    print(f"num_bands is {B}, ranges is {R}")
    
    pipeline = (
        df.rdd
        .flatMap(
            lambda x: generate_hash_values(
                content=x[1],
                idx=x[0],
                num_perm=num_perm,
                ngram_size=ngram_size,
                hashranges=HASH_RANGES,
                permutations = None,
                is_norm = is_norm,
            )
        )
        .groupBy(lambda x: (x[0], x[1]))
        .flatMap(lambda x: generate_edges([(i[2]) for i in x[1]]))
        .flatMap(lambda x: convert_to_slimPJ_fmt(x[0], x[1]))
        .distinct()
    )
    return pipeline

class FuzzyDeduplicate(BaseLLMOperation):
    def __init__(self, text_key = 'text', num_perm = 256, ngram_size = 13, bands = 9, ranges = 13):
        settings = {'text_key': text_key, 'num_perm': 256, 'ngram_size': 3, 'bands': 9, 'ranges': 13}
        super().__init__(settings)        
        self.support_spark = True
        self.support_ray = False
        self.text_key = text_key
        self.inplace = True
        self.num_perm = num_perm
        self.ngram_size = ngram_size
        self.bands = bands
        self.ranges = ranges
    
    def process_spark(self, spark, spark_df: DataFrame) -> DataFrame:
        if self.inplace:
            column_names = spark_df.columns
            if 'norm_text' in column_names:
                is_norm = False
                spark_df = spark_df.select('norm_text', *[n for n in column_names if n != 'norm_text'])
            else:
                is_norm = True
                spark_df = spark_df.select('text', *[n for n in column_names if n != 'text'])
            
            df_with_id = global_unique_id(spark_df, 'filename_docid')
            pipeline = minHashLSH_prepare(df_with_id, self.num_perm, self.ngram_size, self.bands, self.ranges, is_norm)
            with Timer("generate minHashLsh"):
                results = pipeline.collect()
                
            with Timer("generate_connected_components => duplicates"):
                components = generate_connected_components.generate_connected_components_py(results)
                duplicates = [c for c_list in components for c in c_list[1:]]
                R = Row('filename_docid')
                total_dup = len(duplicates)
                if total_dup != 0:
                    duplicates_sdf = spark.createDataFrame([R(dup) for dup in duplicates]).cache()
                    total_dup = duplicates_sdf.count()
                    
            if total_dup == 0:
                ret = df_with_id.drop('filename_docid').cache()
                ret_count = ret.count()
            else:
                with Timer("deduplicate input data"):
                    ret = df_with_id.join(duplicates_sdf, 'filename_docid', 'left_anti').drop('filename_docid').cache()
                    ret_count = ret.count()
            return ret
            
        else:
            raise NotImplementedError("We only support inplace modification for FuzzyDeduplicate.")
    
LLMOPERATORS.register(FuzzyDeduplicate)

class FuzzyDeduplicateGenDict(BaseLLMOperation):
    def __init__(self, text_key = 'text', num_perm = 256, ngram_size = 13, bands = 9, ranges = 13):
        settings = {'text_key': text_key, 'num_perm': 256, 'ngram_size': 3, 'bands': 9, 'ranges': 13}
        super().__init__(settings)        
        self.support_spark = True
        self.support_ray = False
        self.text_key = text_key
        self.inplace = True
        self.num_perm = num_perm
        self.ngram_size = ngram_size
        self.bands = bands
        self.ranges = ranges
    
    def process_spark(self, spark, spark_df: DataFrame) -> DataFrame:
        if self.inplace:
            column_names = spark_df.columns
            if 'norm_text' in column_names:
                is_norm = False
                spark_df = spark_df.select('norm_text', *[n for n in column_names if n != 'norm_text'])
            else:
                is_norm = True
                spark_df = spark_df.select('text', *[n for n in column_names if n != 'text'])
            
            df_with_id = global_unique_id(spark_df, 'filename_docid')
            pipeline = minHashLSH_prepare(df_with_id, self.num_perm, self.ngram_size, self.bands, self.ranges, is_norm)
            with Timer("generate minHashLsh"):
                results = pipeline.collect()
                
            with Timer("generate_connected_components => duplicates"):
                components = generate_connected_components.generate_connected_components_py(results)
                duplicates = [c for c_list in components for c in c_list[1:]]
                R = Row('filename_docid')
                total_dup = len(duplicates)
                if total_dup != 0:
                    duplicates_sdf = spark.createDataFrame([R(dup) for dup in duplicates]).cache()
                    total_dup = duplicates_sdf.count()

            if total_dup == 0:
                from pyspark.sql.types import StructType, StructField, StringType
                ret = spark.createDataFrame(spark.sparkContext.emptyRDD(), StructType([StructField('global_id', StringType(), False)]))
            else:
                with Timer("Get global_id for duplicated data"):
                    ret = df_with_id.join(duplicates_sdf, 'filename_docid', 'inner').select('global_id').cache()
            return ret
            
        else:
            raise NotImplementedError("We only support inplace modification for FuzzyDeduplicate.")
    
LLMOPERATORS.register(FuzzyDeduplicateGenDict)

class FuzzyDeduplicateApplyDict(BaseLLMOperation):
    def __init__(self, text_key = 'text', num_perm = 256, ngram_size = 13, bands = 9, ranges = 13):
        settings = {'text_key': text_key, 'num_perm': 256, 'ngram_size': 3, 'bands': 9, 'ranges': 13}
        super().__init__(settings)        
        self.support_spark = True
        self.support_ray = False
        self.text_key = text_key
        self.inplace = True
        self.num_perm = num_perm
        self.ngram_size = ngram_size
        self.bands = bands
        self.ranges = ranges

    # def execute_spark(self, pipeline, rdp, child_ds=None, global_df=None):
    #     child_output = []
    #     if child_ds is not None:
    #         self.cache = self.process_spark(rdp.spark, child_ds, global_df)
    #     else:
    #         children = self.op.children if self.op.children is not None else []
    #         for op in children:
    #             child_output.append(pipeline[op].cache)
    #         self.cache = self.process_spark(rdp.spark, *child_output)
    #     return self.cache

    def process_spark(self, spark, spark_df: DataFrame, global_df: DataFrame) -> DataFrame:
        if self.inplace:
            column_names = spark_df.columns
            if 'norm_text' in column_names:
                spark_df = spark_df.select('norm_text', *[n for n in column_names if n != 'norm_text'])
            else:
                spark_df = spark_df.select('text', *[n for n in column_names if n != 'text'])

            with Timer("deduplicate input data"):
                ret = spark_df.join(global_df, 'global_id', 'left_anti').cache()
            return ret
        else:
            raise NotImplementedError("We only support inplace modification for FuzzyDeduplicateApplyDict.")
    
LLMOPERATORS.register(FuzzyDeduplicateApplyDict)

def sha256str(s):
    h = hashlib.sha256()
    try:
        h.update(s.encode("utf-8"))
    except UnicodeEncodeError:
        # to avoid things like \ud809\udc50\ud808\udefc\ud808\udedb
        h.update(s.encode("utf-8", "replace"))
    return h.hexdigest()

def global_hash_spk(spark_df, text_key):
    clean_str_udf = F.udf(clean_str, StringType())
    sha256str_udf = F.udf(sha256str, StringType())
    bytesize_udf = F.udf(lambda x: len(x.encode('utf-8')), IntegerType())
    columns = spark_df.columns
    ret_df = spark_df
    ret_df = global_unique_id(ret_df, 'doc_id')
    key = text_key
    is_norm = key != 'norm_text'
    if is_norm:
        ret_df = ret_df.withColumn('hash', sha256str_udf(clean_str_udf(F.col(key))))
    else:
        ret_df = ret_df.withColumn('hash', sha256str_udf(F.col(key)))
    return ret_df

def get_hash_indexing_spk(spark_df):
    dict_df_all = spark_df
    dict_df_all = dict_df_all.groupby('hash').agg(F.collect_list("doc_id").alias('doc_id_list'), F.count("hash").alias('hash_count'))
    return dict_df_all

def get_duplication_list_spk(spark_df):
    dict_df_all = spark_df  
    dict_df_all = dict_df_all.filter("hash_count > 1").cache()
    dict_df_all = dict_df_all.withColumn("doc_id_list", F.slice(F.col("doc_id_list"), 2, F.size(F.col("doc_id_list"))))\
                             .withColumn("doc_id_list", F.explode("doc_id_list"))\
                             .select(F.col("hash"), F.col("doc_id_list").alias("doc_id"))
    return dict_df_all

def index_based_reduction_spk(src_df, dup_df, enable_hash):
    if enable_hash:
        dest_df = src_df.join(dup_df, ["doc_id", "hash"], "left_anti")
    else:
        dest_df = src_df.join(dup_df, "doc_id", "left_anti")
    return dest_df

class GlobalDeduplicate(BaseLLMOperation):
    def __init__(self, text_key = 'text'):        
        settings = {'text_key': text_key}
        super().__init__(settings)
        self.text_key = text_key
        self.inplace = True
        self.support_spark = True
        self.support_ray = False
    
    def process_spark(self, spark, spark_df: DataFrame) -> DataFrame:
        if self.inplace:
            # 1. if input hasn't been processed by global hash
            with Timer(f"Generate Global Hash"):
                hash_df = global_hash_spk(spark_df, self.text_key).cache()
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
                out_df = index_based_reduction_spk(hash_df, ret_df, True).drop('doc_id').cache()
                post_global_dedup_count = out_df.count()                
            return out_df
            
        else:
            raise NotImplementedError("We only support inplace modification for FuzzyDeduplicate.")
    
LLMOPERATORS.register(GlobalDeduplicate)

class GlobalDeduplicateGenDict(BaseLLMOperation):
    def __init__(self, text_key = 'text'):        
        settings = {'text_key': text_key}
        super().__init__(settings)
        self.text_key = text_key
        self.inplace = True
        self.support_spark = True
        self.support_ray = False
    
    def process_spark(self, spark, spark_df: DataFrame) -> DataFrame:
        if self.inplace:
            # 1. if input hasn't been processed by global hash
            with Timer(f"Generate Global Hash"):
                hash_df = global_hash_spk(spark_df, self.text_key).cache()
                post_global_hash_count = hash_df.count()
            
            # 2. get global hash indexing
            with Timer(f"Generate Global indexing based on hash"):
                ret_df = get_hash_indexing_spk(hash_df).cache()
                index_count = ret_df.count()

            # 3. generate duplication indexing
            with Timer(f"Generate global duplication list"):
                ret_df = get_duplication_list_spk(ret_df).cache()
                duplication_count = ret_df.count()
            
            # 4. duplicate rows
            with Timer(f"Generate global duplication rows"):
                out_df = hash_df.join(ret_df, ["doc_id", "hash"], "inner").drop('doc_id').cache()
                post_global_dedup_count = out_df.count()                
            return out_df
            
        else:
            raise NotImplementedError("We only support inplace modification for FuzzyDeduplicate.")
    
LLMOPERATORS.register(GlobalDeduplicateGenDict)

class GlobalDeduplicateApplyDict(BaseLLMOperation):
    def __init__(self, text_key = 'text'):        
        settings = {'text_key': text_key}
        super().__init__(settings)
        self.text_key = text_key
        self.inplace = True
        self.support_spark = True
        self.support_ray = False


    # def execute_spark(self, pipeline, rdp, child_ds=None, global_df=None):
    #     child_output = []
    #     if child_ds is not None:
    #         self.cache = self.process_spark(rdp.spark, child_ds, global_df)
    #     else:
    #         children = self.op.children if self.op.children is not None else []
    #         for op in children:
    #             child_output.append(pipeline[op].cache)
    #         self.cache = self.process_spark(rdp.spark, *child_output)
    #     return self.cache

    def process_spark(self, spark, spark_df: DataFrame, global_df: DataFrame) -> DataFrame:
        if self.inplace:
            # 1. deduplicate input
            with Timer(f"reduce input file based on global duplication rows"):
                ret = spark_df.join(global_df, 'global_id', 'left_anti').cache()
                ret_num = ret.count()
            return ret
        else:
            raise NotImplementedError("We only support inplace modification for FuzzyDeduplicate.")

LLMOPERATORS.register(GlobalDeduplicateApplyDict)