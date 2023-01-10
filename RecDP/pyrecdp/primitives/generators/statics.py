from .base import BaseFeatureGenerator as super_class
from pyrecdp.core import SeriesSchema
from pyrecdp.core.utils import is_text_series
import pandas as pd
import pyarrow as pa
import numpy as np

def draw_xy_scatter_plot(xy_scatter_features, feature_data, y, row_height, n_plot_per_row):
    from plotly.subplots import make_subplots
    import plotly.graph_objs as go
    import math
    
    n_feat = len(xy_scatter_features)
    n_row = math.ceil(n_feat / n_plot_per_row)
    n_col = n_plot_per_row if n_feat > n_plot_per_row else n_feat
    subplot_titles = xy_scatter_features

    fig_list = make_subplots(rows=n_row, cols=n_col, subplot_titles  = subplot_titles, y_title = y.name)

    indices = y.notna()
    if indices.size > 1000:
        frac = 1000/indices.size
        mask = pd.Series(np.random.choice(a=[False, True], size=(indices.size), p=[1-frac, frac]))
        indices = indices & mask

    for idx, c_name in enumerate(xy_scatter_features):
        feature = feature_data[c_name]
        # if string, wrap when too long
        sch = SeriesSchema(feature)
        is_feature_string = True if (sch.is_string or sch.is_categorical_and_string) else False
        
        if is_feature_string:
            tmp = feature[indices].str.slice(0, 12, 1)
            fig = go.Scatter(x=tmp, y=y[indices], mode='markers', name=c_name, showlegend=False)
        else:
            fig = go.Scatter(x=feature[indices], y=y[indices], mode='markers', name=c_name, showlegend=False)

        fig_list.add_trace(fig, row = int(idx / n_plot_per_row) + 1, col = ((idx % n_plot_per_row) + 1))

    fig_list.update_layout(height=row_height * n_row, width=400 * n_col)
    
    return fig_list

def draw_mapbox_plot(mapbox_scatter_features, feature_data):
    import plotly.graph_objs as go
    from shapely.geometry import MultiPoint
    fig_list = go.Figure()
    for c_name in mapbox_scatter_features:
        feature = feature_data[c_name]
        coords = feature.to_list()
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        fig_list.add_trace(
            go.Scattermapbox(
                lat=lats,
                lon=lons,
                name=c_name
            )
        )
        points = MultiPoint(coords)
    fig_list.update_layout(
        autosize=False,
        mapbox=dict(
            style='open-street-map',
            bearing=0,
            center=dict(
                lat=points.centroid.x,
                lon=points.centroid.y
            ),
            pitch=0,
            zoom=8
        ),
    )
        
    return fig_list
class StatisticsFeatureGenerator(super_class):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def is_useful(self, df):
        return True
    
    def fit_prepare(self, pa_schema):
        return
    
    def update_feature_statistics(self, X, y):
        overview_info = {}
        overview_detail = {}
        overview_info['Number of Features'] = X.shape[1]
        overview_info['Number of Rows'] = X.shape[0]
        interactions_detail = self.get_interactive_plot(X, y)
        
        length = X.shape[0]
        for feature_name in X.columns:
            feature = X[feature_name]
            desc_info = dict((k, v) for k, v in feature.describe().to_dict().items() if k not in ['count'])
            if 'unique' in desc_info:
                n_unique = desc_info['unique']
            else:
                n_unique = feature.nunique()

            feature_type = SeriesSchema(feature).dtype_str
            feature_type = "text" if is_text_series(feature) else feature_type
            
            stat = {'type': feature_type, 'unique': {"u": n_unique, "m": length}, 'quantile':desc_info}
            if feature_name not in overview_detail:
                overview_detail[feature_name] = stat
        
        data_stats = {}
        data_stats["overview"] = (overview_info, overview_detail)
        data_stats['interactions']=(dict(), interactions_detail)
        
        return data_stats
    
    def get_interactive_plot(self, feature_data, y):
        from plotly.subplots import make_subplots
        import plotly.graph_objs as go
        from plotly.offline import plot
        row_height = 300
        n_plot_per_row = 2
        
        # we will create types of plot
        xy_scatter_features = []
        mapbox_scatter_features = []
        word_cloud_features = []
        time_series_features = []
        
        for idx, c_name in enumerate(feature_data.columns):
            feature = feature_data[c_name]
            # if string, wrap when too long
            sch = SeriesSchema(feature)
            is_coord = True if sch.is_coordinates else False
            
            if is_coord:
                mapbox_scatter_features.append(c_name)
            else:
                xy_scatter_features.append(c_name)
        
        ret = {}
        ret = {"error": False}

        # draw xy scatter
        if len(xy_scatter_features) > 0:
            fig_list = draw_xy_scatter_plot(xy_scatter_features, feature_data, y, row_height, n_plot_per_row)
            ret['html'] = plot(fig_list, output_type='div')
        
        # draw mapbox
        if len(mapbox_scatter_features) > 0:
            fig_list = draw_mapbox_plot(mapbox_scatter_features, feature_data)
            ret['html'] += plot(fig_list, output_type='div')
        
        return ret
