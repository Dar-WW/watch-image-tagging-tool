#!/bin/bash
# Launch script for Watch Image Tagging Tool

cd "$(dirname "$0")/tagging"
streamlit run app.py
