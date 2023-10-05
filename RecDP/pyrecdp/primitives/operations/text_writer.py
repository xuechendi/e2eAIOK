from .base import BaseLLMOperation, LLMOPERATORS
from ray.data import Dataset
from pyspark.sql import DataFrame
import os
import shutil

class ParquetWriter(BaseLLMOperation):
    def __init__(self, output_dir):
        settings = {'output_dir': output_dir}
        super().__init__(settings)
        self.support_ray = True
        self.support_spark = True
        self.output_dir = output_dir
        
    def process_rayds(self, ds: Dataset) -> Dataset:
        if os.path.exists(self.output_dir) and os.path.isdir(self.output_dir):
            shutil.rmtree(self.output_dir)
        ds.write_parquet(self.output_dir)
        return ds
    
    def process_spark(self, spark, spark_df: DataFrame = None) -> DataFrame:
        spark_df.write.parquet(self.output_dir, mode='overwrite')
        return spark_df
    
LLMOPERATORS.register(ParquetWriter)

class JsonlWriter(BaseLLMOperation):
    def __init__(self, output_dir):
        settings = {'output_dir': output_dir}
        super().__init__(settings)
        self.support_ray = False
        self.support_spark = True
        self.output_dir = output_dir

    def process_rayds(self, ds: Dataset) -> Dataset:
        if os.path.exists(self.output_dir) and os.path.isdir(self.output_dir):
            shutil.rmtree(self.output_dir)
        ds.write_json(self.output_dir)
        return ds

    def process_spark(self, spark, spark_df: DataFrame = None) -> DataFrame:
        spark_df.write.json(self.output_dir, mode='overwrite')
        return spark_df

LLMOPERATORS.register(JsonlWriter)

class PerfileParquetWriter(BaseLLMOperation):
    def __init__(self, output_dir):
        settings = {'output_dir': output_dir}
        super().__init__(settings)
        self.support_ray = True
        self.support_spark = False
        self.output_dir = output_dir
        
    def execute_ray(self, pipeline, source_id):
        child_output = []
        children = self.op.children if self.op.children is not None else []
        for op in children:
            child_output.append(pipeline[op].cache)
        self.cache = self.process_rayds(source_id, *child_output)
        return self.cache
        
    def process_rayds(self, source_id, ds: Dataset) -> Dataset:
        to_save = os.path.join(self.output_dir, source_id)
        if os.path.exists(to_save) and os.path.isdir(to_save):
            shutil.rmtree(to_save)
        ds.write_parquet(os.path.join(self.output_dir, source_id))
        return ds

LLMOPERATORS.register(PerfileParquetWriter)