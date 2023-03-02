from .base import BaseFeatureGenerator as super_class
import pandas as pd
from pyrecdp.core import SeriesSchema
from pyrecdp.primitives.operations import Operation

class CategoryFeatureGenerator(super_class):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.feature_in = []

    def fit_prepare(self, pipeline, children, max_idx):
        is_useful = False
        pa_schema = pipeline[children[0]].output
        feature_out = []
        for pa_field in pa_schema:
            if pa_field.is_categorical_and_string:
                feature = pa_field.name
                out_schema = SeriesSchema(f"{feature}__idx", pd.CategoricalDtype())
                self.feature_in.append(pa_field.name)
                feature_out.append(out_schema)
                is_useful = True
                pa_schema.append(out_schema)
        if is_useful:
            cur_idx = max_idx + 1
            config = self.feature_in
            pipeline[cur_idx] = Operation(cur_idx, children, pa_schema, op = 'categorify', config = config)
            return pipeline, cur_idx, cur_idx
        else:
            return pipeline, children[0], max_idx