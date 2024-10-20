# Copyright 2022 Tier IV, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Script to analyze path
"""
from __future__ import annotations
import sys
import os
import datetime
import pathlib
import shutil
import argparse
from distutils.util import strtobool
import logging
import json
import yaml
import numpy as np
from caret_analyze.record import RecordsInterface
from caret_analyze import Architecture, Application, Lttng
from caret_analyze.plot import Plot
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/..')
from common.utils import create_logger, make_destination_dir, read_trace_data, export_graph, round_yaml

# Suppress log for CARET
from logging import getLogger, FATAL
logger = getLogger()
logger.setLevel(FATAL)

# Suppress log for Bokeh "BokehUserWarning: out of range integer may result in loss of precision"
import warnings
warnings.simplefilter("ignore")

_logger: logging.Logger = None


class Stats():
    def __init__(self, target_path_name: str, node_names: list[str]):
        self.target_path_name = target_path_name
        self.node_names = node_names
        self.best_avg = '---'
        self.best_std = '---'
        self.best_min = '---'
        self.best_max = '---'
        self.best_p50 = '---'
        self.best_p95 = '---'
        self.best_p99 = '---'
        self.worst_avg = '---'
        self.worst_std = '---'
        self.worst_min = '---'
        self.worst_max = '---'
        self.worst_p50 = '---'
        self.worst_p95 = '---'
        self.worst_p99 = '---'
        self.filename_messageflow = ''
        self.filename_messageflow_short = ''
        self.filename_hist_total = ''
        self.filename_hist_best = ''
        self.filename_timeseries_best = ''
        self.filename_stacked_bar_best = ''
        self.filename_hist_worst = ''
        self.filename_timeseries_worst = ''
        self.filename_stacked_bar_worst = ''

    def calc_stats(self, df_best: np.ndarray, df_worst: np.ndarray):
        self.best_avg = round(float(np.average(df_best)), 3)
        if len(df_best) > 1:
            self.best_min = round(float(np.min(df_best)), 3)
            self.best_max = round(float(np.max(df_best)), 3)
            self.best_std = round(float(np.std(df_best)), 3)
            self.best_p50 = round(float(np.quantile(df_best, 0.5)), 3)
            self.best_p95 = round(float(np.quantile(df_best, 0.95)), 3)
            self.best_p99 = round(float(np.quantile(df_best, 0.99)), 3)

        self.worst_avg = round(float(np.average(df_worst)), 3)
        if len(df_worst) > 1:
            self.worst_min = round(float(np.min(df_worst)), 3)
            self.worst_std = round(float(np.std(df_worst)), 3)
            self.worst_max = round(float(np.max(df_worst)), 3)
            self.worst_p50 = round(float(np.quantile(df_worst, 0.5)), 3)
            self.worst_p95 = round(float(np.quantile(df_worst, 0.95)), 3)
            self.worst_p99 = round(float(np.quantile(df_worst, 0.99)), 3)

    def store_filename(self, target_path_name: str, save_long_graph: bool):
        if save_long_graph:
            self.filename_messageflow = f'{target_path_name}_messageflow'
        self.filename_messageflow_short = f'{target_path_name}_messageflow_short'
        self.filename_hist_best = f'{target_path_name}_hist_best'
        self.filename_timeseries_best = f'{target_path_name}_timeseries_best'
        self.filename_stacked_bar_best = f'{target_path_name}_stacked_bar_best'
        self.filename_hist_worst = f'{target_path_name}_hist_worst'
        self.filename_timeseries_worst = f'{target_path_name}_timeseries_worst'
        self.filename_stacked_bar_worst = f'{target_path_name}_stacked_bar_worst'


def get_messageflow_durationtime(records: RecordsInterface, check_by_input: bool = True):
    """Get duration time [sec] of message flow"""
    df_records = records.to_dataframe()
    try:
        input_column = df_records.columns[0]
        input_time_min = df_records[input_column].min()
        if check_by_input:
            input_time_max = df_records[input_column].max()
            duration = (input_time_max - input_time_min) * 1e-9
        else:
            output_column = df_records.columns[-1]
            output_time_max = df_records[output_column].max()
            duration = (output_time_max - input_time_min) * 1e-9
    except:
        duration = None

    if not isinstance(duration, (int, float)):
        duration = None

    return duration


def check_the_first_last_callback_is_valid(records: RecordsInterface):
    df_records = records.to_dataframe()
    is_first_valid = True
    is_last_valid = True
    if len(df_records[df_records.columns[0]]) == 0:
        # velodyne_convert_node doesn't have the first callback_start
        _logger.warning(f'  The first callback is invalid')
        is_first_valid = False
    if len(df_records[df_records.columns[-1]]) == 0:
        _logger.warning(f'  The last callback is invalid')
        is_last_valid = False
    return is_first_valid, is_last_valid


def analyze_path(args, dest_dir: str, arch: Architecture, app: Application, target_path_name: str, include_first_last_callback: dict, xaxis_type: str):
    """Analyze a path"""
    _logger.info(f'Processing: {target_path_name}')
    target_path = app.get_path(target_path_name)

    # Include the first and last callback if availble
    target_path.include_first_callback = include_first_last_callback[target_path_name][0]
    target_path.include_last_callback = include_first_last_callback[target_path_name][1]
    records = target_path.to_records()
    is_first_valid, is_last_valid = check_the_first_last_callback_is_valid(records)
    if (not is_first_valid) or (not is_last_valid):
        target_path.include_first_callback = is_first_valid
        target_path.include_last_callback = is_last_valid
        records = target_path.to_records()

    stats = Stats(target_path_name, arch.get_path(target_path_name).node_names)

    _logger.info('  message flow')
    duration = get_messageflow_durationtime(records)
    if duration is None:
        _logger.warning(f'    No-traffic and No-input in the path: {target_path_name}')
        return stats

    graph_short = Plot.create_message_flow_plot(target_path,
                lstrip_s=duration / 2,
                rstrip_s=max(duration / 2 - (3 + 0.1), 0)).figure(full_legends=True)
    message_flow_height = 18 * len(target_path.child_names) + 50
    graph_short.frame_height = message_flow_height  # height doesn't work for some reasons...
    export_graph(graph_short, dest_dir, f'{target_path_name}_messageflow_short', target_path_name, with_png=False)

    if args.message_flow:
        graph = Plot.create_message_flow_plot(target_path).figure(full_legends=True)
        graph.frame_height = message_flow_height
        export_graph(graph, dest_dir, f'{target_path_name}_messageflow', target_path_name, with_png=False)

    _logger.info('  response time')
    if get_messageflow_durationtime(records, check_by_input=False) is None:
        _logger.warning(f'    No-traffic in the path: {target_path_name}')
    else:
        df_response_time = {}
        for case_str in ['best', 'worst', 'all']:
            plot_timeseries = Plot.create_response_time_timeseries_plot(target_path, case=case_str)
            plot_timeseries.to_dataframe(
                xaxis_type=xaxis_type).to_csv(
                f'{dest_dir}/{target_path_name}_response_time_{case_str}.csv')
            fig_timeseries = plot_timeseries.figure(full_legends=False, xaxis_type=xaxis_type)
            df_response_time[case_str] = plot_timeseries.to_dataframe(xaxis_type=xaxis_type)
            fig_hist = Plot.create_response_time_histogram_plot(target_path, case=case_str).figure(full_legends=False, xaxis_type=xaxis_type)
            fig_timeseries.y_range.start = 0
            fig_timeseries.legend.visible = False
            fig_hist.legend.visible = False
            fig_timeseries.frame_width = 500  # width doesn't work for some reasons...
            fig_timeseries.frame_height = 320  # height doesn't work for some reasons...
            fig_hist.width = 600
            fig_hist.height = 400
            export_graph(fig_timeseries, dest_dir, target_path_name + f'_timeseries_{case_str}', target_path_name, with_png=False)
            export_graph(fig_hist, dest_dir, target_path_name + f'_hist_{case_str}', target_path_name, with_png=False)
            try:
                Plot.create_response_time_stacked_bar_plot(target_path, case=case_str).save(xaxis_type=xaxis_type, export_path=f'{dest_dir}/{target_path_name}_stacked_bar_{case_str}.html', full_legends=True)
            except Exception as e:
                _logger.warning(f'    Failed to create stacked bar graph: {target_path_name}, {case_str}')
                _logger.warning(str(e))
        stats.calc_stats(df_response_time['best'].iloc[:, 1], df_response_time['worst'].iloc[:, 1])

    stats.store_filename(target_path_name, args.message_flow)
    _logger.info(f'---{target_path_name}---')
    _logger.debug(vars(stats))

    return stats


def get_include_first_last_callback(args, arch: Architecture):
    include_first_last_callback = {}
    for target_path in arch.paths:
        target_path_name = target_path.path_name
        include_first_last_callback[target_path_name] = (True, True)

    def modify_dictionary(dictionary, target_string, new_value):
        for key in dictionary:
            if target_string in key:
                dictionary[key] = new_value

    with open(args.target_path_json, encoding='UTF-8') as f_json:
        target_path_json = json.load(f_json)
        for target_path in target_path_json['target_path_list']:
            target_path_name = target_path['name']
            include_first_callback = target_path['include_first_callback'] if 'include_first_callback' in target_path else True
            include_last_callback = target_path['include_last_callback'] if 'include_last_callback' in target_path else True
            modify_dictionary(include_first_last_callback, target_path_name, (include_first_callback, include_last_callback))

    return include_first_last_callback


def analyze(args, lttng: Lttng, arch: Architecture, app: Application, dest_dir: str):
    """Analyze paths"""
    global _logger
    if _logger is None:
        _logger = create_logger(__name__, logging.DEBUG if args.verbose else logging.INFO)
    _logger.info('<<< Analyze Paths: Start >>>')
    xaxis_type =  'sim_time' if args.sim_time else 'system_time'
    make_destination_dir(dest_dir, args.force, _logger)
    shutil.copy(args.architecture_file_path, dest_dir)

    include_first_last_callback = get_include_first_last_callback(args, arch)

    stats_list = []

    # Verify each path
    for target_path in arch.paths:
        target_path_name = target_path.path_name
        path = arch.get_path(target_path_name)
        ret_verify = path.verify()
        _logger.info(f'path.verify {target_path_name}: {ret_verify}')
        if not ret_verify:
            sys.exit(-1)

    # Analyze each path
    for target_path in arch.paths:
        target_path_name = target_path.path_name
        stats = analyze_path(args, dest_dir, arch, app, target_path_name, include_first_last_callback, xaxis_type)
        stats_list.append(vars(stats))

    # Save stats file
    stat_file_path = f'{dest_dir}/stats_path.yaml'
    with open(stat_file_path, 'w', encoding='utf-8') as f_yaml:
        yaml.safe_dump(stats_list, f_yaml, encoding='utf-8', allow_unicode=True, sort_keys=False)
    round_yaml(stat_file_path)

    _logger.info('<<< Analyze Paths: Finish >>>')


def parse_arg():
    """Parse arguments"""
    parser = argparse.ArgumentParser(
                description='Script to analyze path')
    parser.add_argument('trace_data', nargs=1, type=str)
    parser.add_argument('dest_dir', nargs=1, type=str)
    parser.add_argument('--target_path_json', type=str, default='target_path.json')
    parser.add_argument('--architecture_file_path', type=str, default='architecture_path.yaml')
    parser.add_argument('-m', '--message_flow', type=strtobool, default=False,
                        help='Output message flow graph')
    parser.add_argument('--start_strip', type=float, default=0.0,
                        help='Start strip [sec] to load trace data')
    parser.add_argument('--end_strip', type=float, default=0.0,
                        help='End strip [sec] to load trace data')
    parser.add_argument('--sim_time', type=strtobool, default=False)
    parser.add_argument('-f', '--force', action='store_true', default=False,
                        help='Overwrite report directory')
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    args = parser.parse_args()
    return args


def main():
    """Main function"""
    global _logger
    args = parse_arg()
    _logger = create_logger(__name__, logging.DEBUG if args.verbose else logging.INFO)

    _logger.debug(f'trace_data: {args.trace_data[0]}')
    _logger.debug(f'dest_dir: {args.dest_dir[0]}')
    _logger.debug(f'target_path_json: {args.target_path_json}')
    _logger.debug(f'architecture_file_path: {args.architecture_file_path}')
    _logger.debug(f'start_strip: {args.start_strip}, end_strip: {args.end_strip}')
    _logger.debug(f'sim_time: {args.sim_time}')
    args.message_flow = True if args.message_flow == 1 else False
    _logger.debug(f'message_flow: {args.message_flow}')

    lttng = read_trace_data(args.trace_data[0], args.start_strip, args.end_strip, False)
    arch = Architecture('yaml', args.architecture_file_path)
    app = Application(arch, lttng)

    dest_dir = args.dest_dir[0]
    analyze(args, lttng, arch, app, dest_dir + '/analyze_path')


if __name__ == '__main__':
    main()
