"""Generate poster with ArUco markers from JSON specification"""

import cv2
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
import json
import argparse
import os
import sys

# ArUco dictionary
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)

def generate_aruco_marker(marker_id, size_pixels=200):
    """Generate an ArUco marker image"""
    marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, size_pixels)
    return marker_img

def load_marker_config(json_file):
    """Load marker configuration from JSON file"""
    with open(json_file, 'r') as f:
        config = json.load(f)
    return config

def create_poster(config_file):
    """Create poster with ArUco markers from JSON configuration"""
    
    # Load configuration
    config = load_marker_config(config_file)
    
    # Get surface dimensions
    width_mm = config['surface']['width']
    height_mm = config['surface']['height']
    markers = config['markers']
    
    # Create output filename based on input filename
    base_name = os.path.splitext(config_file)[0]
    pdf_filename = f"{base_name}.pdf"
    
    # Create PDF with custom size
    # ReportLab uses points (1/72 inch), convert mm to points
    width_pts = width_mm * mm
    height_pts = height_mm * mm
    
    c = canvas.Canvas(pdf_filename, pagesize=(width_pts, height_pts))
    
    # Keep track of temporary files for cleanup
    temp_files = []
    
    # Generate and place markers
    for marker in markers:
        marker_id = marker['id']
        marker_size_mm = marker['size']
        x_mm = marker['position']['x']
        y_mm = marker['position']['y']
        
        # Generate marker image (higher resolution for better quality)
        marker_img = generate_aruco_marker(marker_id, size_pixels=400)
        
        # Save to temporary file
        temp_filename = f"temp_marker_{marker_id}.png"
        cv2.imwrite(temp_filename, marker_img)
        temp_files.append(temp_filename)
        
        # Calculate position (bottom-left corner of marker)
        # JSON position is center of marker
        x_pts = (x_mm - marker_size_mm / 2) * mm
        y_pts = (y_mm - marker_size_mm / 2) * mm
        size_pts = marker_size_mm * mm
        
        # Draw marker on PDF
        c.drawImage(temp_filename, x_pts, y_pts, width=size_pts, height=size_pts)
        
        # Add small label below marker
        label_y = y_pts - 10 * mm
        c.setFont("Helvetica", 10)
        c.drawCentredString(x_pts + size_pts/2, label_y, f"ID: {marker_id}")
    
    # Save PDF
    c.save()
    
    # Clean up temporary files
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    print(f"Poster saved to {pdf_filename}")
    print(f"Size: {width_mm}mm × {height_mm}mm")
    print(f"Markers: {len(markers)} total")
    for marker in markers:
        print(f"  ID {marker['id']}: {marker['size']}mm at ({marker['position']['x']}, {marker['position']['y']})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Generate PDF poster with ArUco markers from JSON configuration'
    )
    parser.add_argument(
        'config_file',
        help='JSON file containing marker configuration (e.g., markers_a0.json)'
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.config_file):
        print(f"Error: Configuration file '{args.config_file}' not found")
        sys.exit(1)
    
    create_poster(args.config_file)