# -*- coding: utf-8 -*-
"""
Created on Mon Nov 25 10:46:02 2024

@author: simon

To make a simple dashboard for public information

required package
!pip install plotly=5.24.1

Env export:
!conda env export > OMERO_GU.yml

Local sever: http://127.0.0.1:5000

"""

from flask import Flask, render_template, request, jsonify
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import random
from datetime import datetime, timedelta


app = Flask(__name__)

# Database connection function
def get_db_connection():
    conn = sqlite3.connect('omero_imports.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/update_dashboard')
def update_dashboard():
    time_period = request.args.get('time_period', 'last_year')
    granularity = request.args.get('granularity', 'month')
    microscope = request.args.get('microscope', 'all')

    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM imports", conn)
    conn.close()

    df['time'] = pd.to_datetime(df['time'])
    
    # Filter data based on time period
    if time_period == 'last_year':
        df = df[df['time'] > (pd.Timestamp.now() - pd.DateOffset(years=1))]
    elif time_period == 'last_month':
        df = df[df['time'] > (pd.Timestamp.now() - pd.DateOffset(months=1))]
    elif time_period == 'last_week':
        df = df[df['time'] > (pd.Timestamp.now() - pd.DateOffset(weeks=1))]

    # Filter by microscope if specified
    if microscope != 'all':
        df = df[df['scope'] == microscope]

    # Group by time based on granularity
    if granularity == 'day':
        df['time_group'] = df['time'].dt.date
    elif granularity == 'week':
        df['time_group'] = df['time'].dt.to_period('W').apply(lambda r: r.start_time)
    elif granularity == 'month':
        df['time_group'] = df['time'].dt.to_period('M').apply(lambda r: r.start_time)
    elif granularity == 'year':
        df['time_group'] = df['time'].dt.to_period('Y').apply(lambda r: r.start_time)

    # Calculate metrics
    grouped = df.groupby('time_group').agg({
        'file_count': 'sum',
        'total_file_size_mb': 'sum'
    }).reset_index()
    
    grouped.columns = ['time_group', 'file_count', 'total_upload']

    # Create charts with hidden x-axis
    file_count_chart = px.bar(grouped, x='time_group', y='file_count', title='Number of Uploaded Files')
    file_count_chart.update_xaxes(visible=False)
    file_count_chart.update_layout(
                                   yaxis_title='Number of Files',
                                   barmode='group',  # Use 'stack' for stacked bars
                                   )

    total_upload_chart = px.bar(grouped, x='time_group', y='total_upload', title='Total Upload Size')
    total_upload_chart.update_xaxes(visible=False)
    total_upload_chart.update_layout(
                                     yaxis_title='MB',
                                     )
    
    
    return jsonify({
        'file_count_chart': file_count_chart.to_json(),
        'total_upload_chart': total_upload_chart.to_json()
    })
    

@app.route('/get_microscopes')
def get_microscopes():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT scope FROM imports")
    microscopes = [row['scope'] for row in cursor.fetchall()]
    conn.close()
    return jsonify({'microscopes': microscopes})


@app.route('/check_data')
def check_data():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM imports LIMIT 5", conn)
    conn.close()
    return df.to_html()


def initialize_database(db_name='omero_imports.db'):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            username TEXT NOT NULL,
            groupname TEXT NOT NULL,
            scope TEXT NOT NULL,
            file_count INTEGER NOT NULL,
            total_file_size_mb REAL NOT NULL,
            import_time_s REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def insert_random_data_with_peaks(db_name='omero_imports.db', num_days=730):
    initialize_database()
    
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Define the scopes and other constant fields
    scopes = ['LSM980', 'LSM880']
    username = 'test'
    groupname = 'test'

    # Start from today and go back num_days
    start_date = datetime.now() - timedelta(days=num_days)

    for day in range(num_days):
        current_date = start_date + timedelta(days=day)
        date_str = current_date.strftime('%Y-%m-%d %H:%M:%S')

        # Determine if this day is a peak day (e.g., more activity during certain months)
        month = current_date.month
        is_peak_season = month in [3, 5, 6, 12]  # Assume higher activity
        
        if random.random() > .5 and not is_peak_season: #more randomness
            continue
        
        # Generate random data for each scope with peaks
        for scope in scopes:
            if random.random() > .5: #more randomness
                continue
            if is_peak_season:
                file_count = random.randint(5, 30)  # More uploads during peak season
            else:
                file_count = random.randint(1, 5)  # Fewer uploads during off-peak


            total_file_size_mb = round(random.uniform(0.5 * file_count, 5.0 * file_count), 2)
            import_time_s = round(random.uniform(1.0, 10.0), 2)

            cursor.execute('''
                INSERT INTO imports (time, username, groupname, scope, file_count, total_file_size_mb, import_time_s)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (date_str, username, groupname, scope, file_count, total_file_size_mb, import_time_s))

    conn.commit()
    conn.close()



if __name__ == '__main__':
    app.run(debug=True)
    pass