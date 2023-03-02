from .base import BaseOperation
import pandas as pd

class MergeOperation(BaseOperation):
    def __init__(self, op_base):
        super().__init__(op_base)
        self.config = op_base.config
        
    def execute_pd(self, pipeline):
        if self.cache is not None:
            return
        
        if len(self.op.children) != 2:
            raise ValueError("merge operation only accept num_children as 2")
        left_child = pipeline[self.op.children[0]].cache
        right_child = pipeline[self.op.children[1]].cache
        self.cache = pd.merge(left_child, right_child, on = self.config['on'], how = self.config['how'])

    def execute_spark(self, pipeline, rdp):
        if self.cache is not None:
            return
        
        if len(self.op.children) != 2:
            raise ValueError("merge operation only accept num_children as 2")
        
        left_child = pipeline[self.op.children[0]].cache
        right_child = pipeline[self.op.children[1]].cache
    
        self.cache = left_child.join(right_child, on = self.config['on'], how = self.config['how'])