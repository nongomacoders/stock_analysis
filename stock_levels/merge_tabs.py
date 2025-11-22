import glob
import os

def combine_tab_files():
    # Define the pattern to match files (files starting with 'tab' and ending in .py)
    search_pattern = "tab*.py"
    
    # Define the name of the resulting file
    output_filename = "combined_output.py"

    # Find all files matching the pattern
    files_to_combine = glob.glob(search_pattern)
    
    # Sort the files to ensure they are added in a predictable order (tab1, tab2, etc.)
    files_to_combine.sort()

    if not files_to_combine:
        print("No files found starting with 'tab'.")
        return

    print(f"Found {len(files_to_combine)} files. Starting combination...")

    # Open the output file in write mode
    with open(output_filename, "w", encoding="utf-8") as outfile:
        # Add a header to the main file
        outfile.write(f"# Combined Python Script\n")
        outfile.write(f"# Generated from files matching: {search_pattern}\n\n")

        for filename in files_to_combine:
            # Prevent the script from trying to combine the output file if it matches the pattern
            if filename == output_filename:
                continue
            
            try:
                with open(filename, "r", encoding="utf-8") as infile:
                    content = infile.read()
                    
                    # Create a visual separator and comment indicating the source file
                    outfile.write(f"\n{'#' * 60}\n")
                    outfile.write(f"# SOURCE FILE: {filename}\n")
                    outfile.write(f"{'#' * 60}\n\n")
                    
                    # Write the content of the file
                    outfile.write(content)
                    
                    # Add extra newlines for separation between files
                    outfile.write("\n\n")
                    
                    print(f" -> Added: {filename}")
            
            except Exception as e:
                print(f"Error reading {filename}: {e}")

    print(f"\nSuccess! All files have been combined into '{output_filename}'")

if __name__ == "__main__":
    combine_tab_files()