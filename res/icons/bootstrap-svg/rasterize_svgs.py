import os
import sys
import glob
import re
import concurrent.futures

try:
    import cairosvg
except ImportError:
    print("Error: 'cairosvg' library is not installed.")
    print("Please install it using: pip install cairosvg")
    print("Note: On Windows, CairoSVG requires GTK+3 to be installed on your system.")
    print("You can download the GTK3 runtime from: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer")
    sys.exit(1)

def process_svg(svg_file, output_dir, width, height, color_input):
    try:
        with open(svg_file, 'r', encoding='utf-8') as f:
            svg_data = f.read()

        # Replace any existing fill attributes directly
        svg_data = re.sub(r'fill="[^"]*"', f'fill="{color_input}"', svg_data)
        # Replace any existing stroke attributes if they exist
        svg_data = re.sub(r'stroke="[^"]*"', f'stroke="{color_input}"', svg_data)
        # Replace currentcolor with our hex code (common in bootstrap icons)
        svg_data = re.sub(r'currentColor', color_input, svg_data, flags=re.IGNORECASE)

        # Insert a global CSS style block right after the opening <svg> tag to force overrides
        style_tag = f"<style> * {{ fill: {color_input} !important; }} </style>"
        svg_data = re.sub(r'(<svg[^>]*>)', r'\1\n' + style_tag, svg_data, count=1, flags=re.IGNORECASE)

        # Define output path
        base_name = os.path.splitext(svg_file)[0]
        output_file = os.path.join(output_dir, f"{base_name}.png")

        # Rasterize
        # background_color=None ensures a transparent background
        cairosvg.svg2png(
            bytestring=svg_data.encode('utf-8'),
            write_to=output_file,
            output_width=width,
            output_height=height,
            parent_width=width,
            parent_height=height,
            background_color=None 
        )
        return f"Rasterized: {svg_file} -> {output_file}"
    except Exception as e:
        return f"Failed to process {svg_file}: {e}"

def main():
    # 1. Ask for resolution with defaults
    res_input = input("Enter resolution (e.g. 512x512) [Default: 512x512]: ").strip()
    if not res_input:
        res_input = "512x512"
        
    if 'x' in res_input.lower():
        parts = res_input.lower().split('x')
        width = int(parts[0])
        height = int(parts[1])
    else:
        width = int(res_input)
        height = int(res_input)

    # 2. Ask for hex color with defaults
    color_input = input("Enter hexadecimal color code (e.g. #FF0000) [Default: #FFFFFF]: ").strip()
    if not color_input:
        color_input = "#FFFFFF"
        
    if not color_input.startswith('#'):
        color_input = '#' + color_input
    
    # Format the hex code for the directory name (remove #)
    hex_clean = color_input.replace('#', '').upper()

    # 3. Create output directory
    output_dir = f"svg_render_{width}x{height}_{hex_clean}"
    os.makedirs(output_dir, exist_ok=True)

    # 4. Find all SVGs in current directory
    svg_files = glob.glob("*.svg")
    if not svg_files:
        print("No SVG files found in the current directory.")
        return

    cpu_cores = os.cpu_count() or 4
    print(f"Found {len(svg_files)} SVG files.")
    print(f"Rasterizing to {width}x{height} with fill color {color_input}...")
    print(f"Using multithreading with {cpu_cores} concurrent workers...")
    print(f"Output directory: {output_dir}")
    print("-" * 40)

    # 5. Process each SVG concurrently using multithreading
    with concurrent.futures.ThreadPoolExecutor(max_workers=cpu_cores) as executor:
        # Submit all tasks
        futures = [executor.submit(process_svg, svg_file, output_dir, width, height, color_input) for svg_file in svg_files]
        
        # Wait for completion and print results
        for future in concurrent.futures.as_completed(futures):
            print(future.result())

    print("-" * 40)
    print("Done!")

if __name__ == "__main__":
    main()
