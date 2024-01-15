#!/bin/sh

# Create analysis report
script_path=../report/report_analysis
export component_list_json=./component_list.json
export target_path_json=./target_path.json
export max_node_depth=20
export timeout=120
export draw_all_message_flow=false
export report_store_dir=./output
export relpath_from_report_store_dir=false
export sim_time=false
export note_text_top=./note_text_top.txt
export note_text_bottom=./note_text_bottom.txt
export start_strip=0
export end_strip=0

export trace_data=/home/atsushi/caret_report/sample_autoware/trace_data/session-20240115125126-odaiba-cfs-00
sh ${script_path}/make_report.sh

