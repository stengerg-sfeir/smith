#!/usr/bin/env python3
import click
import csv
import json
import sqlite3
import sys
from typing import Optional, Dict, List

@click.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--output', 'output_file', type=click.Path(), default=None, help='Output JSON file path. If not provided, output is printed to stdout.')
def main(input_file: str, output_file: Optional[str]) -> None:
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            if not headers:
                click.echo("Error: Empty CSV file.", err=True)
                sys.exit(1)

            data: List[Dict[str, str]] = []
            for row in reader:
                row_data = {}
                for header in headers:
                    # Handle potential missing values in CSV
                    row_data[header] = row.get(header, None)
                data.append(row_data)

            # Output JSON
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as out_f:
                    json.dump(data, out_f, indent=2, ensure_ascii=False)
                click.echo(f"Data successfully written to {output_file}")
            else:
                click.echo(json.dumps(data, indent=2, ensure_ascii=False))

    except FileNotFoundError:
        click.echo(f"Error: Input file '{input_file}' not found.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error processing file: {str(e)}", err=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
