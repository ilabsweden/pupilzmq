"""Generate A0 landscape poster with ArUco markers"""

import cv2
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A0, landscape
import io
from PIL import Image

# A0 landscape dimensions in mm
A0_WIDTH_MM = 1189
A0_HEIGHT_MM = 841

# Marker size in mm
MARKER_SIZE_MM = 50

# ArUco dictionary
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)

def generate_aruco_marker(marker_id, size_pixels=200):
    """Generate an ArUco marker image"""
    marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, size_pixels)
    return marker_img

def create_poster():
    """Create A0 poster with 8 ArUco markers"""
    
    # Create PDF with A0 landscape
    pdf_filename = "aruco_poster_a0.pdf"
    c = canvas.Canvas(pdf_filename, pagesize=landscape(A0))
    width_pts, height_pts = landscape(A0)
    
    # Convert to mm for easier calculation
    width_mm = A0_WIDTH_MM
    height_mm = A0_HEIGHT_MM
    
    # Marker positions (center of each marker in mm)
    # 3 markers along top edge
    top_y = 100  # Distance from top edge
    top_positions = [
        (width_mm * 0.25, height_mm - top_y),  # Left-top
        (width_mm * 0.5, height_mm - top_y),   # Center-top
        (width_mm * 0.75, height_mm - top_y)   # Right-top
    ]
    
    # 3 markers along bottom edge
    bottom_y = 100  # Distance from bottom edge
    bottom_positions = [
        (width_mm * 0.25, bottom_y),  # Left-bottom
        (width_mm * 0.5, bottom_y),   # Center-bottom
        (width_mm * 0.75, bottom_y)   # Right-bottom
    ]
    
    # 2 markers centrally placed (left and right halves)
    center_y = height_mm / 2
    center_positions = [
        (width_mm * 0.25, center_y),  # Left-center
        (width_mm * 0.75, center_y)   # Right-center
    ]
    
    # Combine all positions (8 markers total, IDs 1-8)
    all_positions = top_positions + center_positions + bottom_positions
    
    # Generate and place markers
    for i, (x_mm, y_mm) in enumerate(all_positions):
        marker_id = i + 1
        
        # Generate marker image (higher resolution for better quality)
        marker_img = generate_aruco_marker(marker_id, size_pixels=400)
        
        # Save to temporary file
        temp_filename = f"temp_marker_{marker_id}.png"
        cv2.imwrite(temp_filename, marker_img)
        
        # Calculate position (bottom-left corner of marker)
        x_pts = (x_mm - MARKER_SIZE_MM / 2) * mm
        y_pts = (y_mm - MARKER_SIZE_MM / 2) * mm
        size_pts = MARKER_SIZE_MM * mm
        
        # Draw marker on PDF
        c.drawImage(temp_filename, x_pts, y_pts, width=size_pts, height=size_pts)
        
        # Add small label below marker
        label_y = y_pts - 10 * mm
        c.setFont("Helvetica", 10)
        c.drawCentredString(x_pts + size_pts/2, label_y, f"ID: {marker_id}")
    
    # Save PDF
    c.save()
    
    # Clean up temporary files
    import os
    for i in range(1, 9):
        temp_file = f"temp_marker_{i}.png"
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    print(f"Poster saved to {pdf_filename}")
    print(f"Size: A0 landscape ({A0_WIDTH_MM}mm × {A0_HEIGHT_MM}mm)")
    print(f"Markers: 8 (IDs 1-8), each {MARKER_SIZE_MM}mm × {MARKER_SIZE_MM}mm")
    print("\nMarker layout:")
    print("  Top edge: 3 markers (IDs 1, 2, 3)")
    print("  Center: 2 markers (IDs 4, 5)")
    print("  Bottom edge: 3 markers (IDs 6, 7, 8)")

if __name__ == "__main__":
    create_poster()
