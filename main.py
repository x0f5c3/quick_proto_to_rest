# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "click",
#     "rich",
# ]
# ///

import re
import sys
import json
import logging
import subprocess
import click
from rich.logging import RichHandler

# --- Logging Configuration ---

class JsonFormatter(logging.Formatter):
    """Custom formatter to output logs in JSON format for file logging."""
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

def setup_logging(verbose: bool, log_file: str):
    """Sets up dual logging: Rich (console/stderr) and JSON (file)."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # 1. Console Handler (Rich) - writes to stderr to allow piping stdout
    console_handler = RichHandler(
        rich_tracebacks=True, 
        markup=True,
        show_path=False,
        console=click.get_current_context().find_root().obj # Use context if needed, or default
    )
    console_format = "%(message)s"
    console_handler.setFormatter(logging.Formatter(console_format))
    root_logger.addHandler(console_handler)

    # 2. File Handler (JSON)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JsonFormatter())
        root_logger.addHandler(file_handler)

# --- Converter Logic ---

def to_camel_case(snake_str):
    components = snake_str.split('_')
    return ''.join(x.title() for x in components)

def map_type(proto_type):
    type_mapping = {
        'double': 'float64',
        'float': 'float32',
        'int32': 'int32',
        'int64': 'int64',
        'uint32': 'uint32',
        'uint64': 'uint64',
        'sint32': 'int32',
        'sint64': 'int64',
        'fixed32': 'uint32',
        'fixed64': 'uint64',
        'sfixed32': 'int32',
        'sfixed64': 'int64',
        'bool': 'bool',
        'string': 'string',
        'bytes': '[]byte',
        # Well-known types mapping
        'google.protobuf.Timestamp': 'time.Time',
        'Timestamp': 'time.Time',
    }
    return type_mapping.get(proto_type, proto_type)

def run_gofmt(code: str) -> str:
    """Formats Go code using gofmt via stdin/stdout without temp files."""
    logger = logging.getLogger("converter")
    
    try:
        # Run gofmt, passing code to stdin
        process = subprocess.run(
            ["gofmt"],
            input=code.encode("utf-8"),
            capture_output=True,
            check=True
        )
        logger.info("Code formatted successfully with gofmt.")
        return process.stdout.decode("utf-8")
        
    except FileNotFoundError:
        logger.warning("The 'gofmt' executable was not found in PATH. Skipping formatting.")
        return code
    except subprocess.CalledProcessError as e:
        logger.error(f"gofmt failed to format code:\n{e.stderr.decode('utf-8')}")
        # Return original code if formatting fails, so the user doesn't lose output
        return code

def parse_proto_and_generate_go(input_file, package_name):
    logger = logging.getLogger("converter")
    logger.info(f"Starting conversion for file: [bold cyan]{input_file}[/]", extra={"markup": True})

    try:
        with open(input_file, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        logger.critical(f"Input file not found: {input_file}")
        sys.exit(1)

    imports = {"\"context\""}
    body_code = []
    
    state = "NONE" # NONE, MESSAGE, SERVICE, ENUM
    current_enum_name = ""
    is_first_enum_field = False
    
    message_regex = re.compile(r'message\s+(\w+)\s*\{')
    service_regex = re.compile(r'service\s+(\w+)\s*\{')
    enum_regex = re.compile(r'enum\s+(\w+)\s*\{')
    
    # Regex fields
    field_regex = re.compile(r'\s*(repeated)?\s*([\w\.]+)\s+(\w+)\s*=\s*\d+;')
    rpc_regex = re.compile(r'\s*rpc\s+(\w+)\s*\(([^)]+)\)\s*returns\s*\(([^)]+)\)')
    enum_field_regex = re.compile(r'\s*(\w+)\s*=\s*\d+;')
    
    line_count = 0

    for line in lines:
        line_count += 1
        raw_line = line.strip()
        
        if not raw_line or raw_line.startswith('//'):
            continue

        parts = raw_line.split('//', 1)
        code_part = parts[0].strip()
        comment_part = parts[1].strip() if len(parts) > 1 else ""

        if not code_part:
            continue

        # Detect Message
        msg_match = message_regex.search(code_part)
        if msg_match:
            struct_name = msg_match.group(1)
            logger.debug(f"Found message definition: [green]{struct_name}[/]", extra={"markup": True})
            body_code.append(f"// {struct_name} represents the {struct_name} model from proto")
            body_code.append(f"type {struct_name} struct {{")
            state = "MESSAGE"
            continue

        # Detect Enum
        enum_match = enum_regex.search(code_part)
        if enum_match:
            current_enum_name = enum_match.group(1)
            logger.debug(f"Found enum definition: [yellow]{current_enum_name}[/]", extra={"markup": True})
            body_code.append(f"// {current_enum_name} is an enumeration based on byte")
            body_code.append(f"type {current_enum_name} byte")
            body_code.append("const (")
            state = "ENUM"
            is_first_enum_field = True
            continue

        # Detect Service
        svc_match = service_regex.search(code_part)
        if svc_match:
            service_name = svc_match.group(1)
            logger.info(f"Found service definition: [blue]{service_name}[/]", extra={"markup": True})
            body_code.append(f"// {service_name} defines the interface for the REST client/server")
            body_code.append(f"type {service_name} interface {{")
            state = "SERVICE"
            continue

        # Detect End Block
        if code_part == '}' and state in ["MESSAGE", "SERVICE", "ENUM"]:
            if state == "ENUM":
                body_code.append(")") # Close const block
            else:
                body_code.append("}") # Close struct/interface
            
            body_code.append("")
            state = "NONE"
            continue

        # Process Message Fields
        if state == "MESSAGE":
            field_match = field_regex.search(code_part)
            if field_match:
                is_repeated = field_match.group(1) == 'repeated'
                proto_type = field_match.group(2)
                field_name = field_match.group(3)
                
                go_type = map_type(proto_type)
                
                # Handle imports for known types
                if go_type == "time.Time":
                    imports.add("\"time\"")
                
                # Check for UUID hint
                if "UUID" in comment_part.upper():
                    logger.debug(f"Detected UUID field: {field_name} in struct")
                    go_type = "uuid.UUID"
                    imports.add("\"github.com/google/uuid\"")
                
                if is_repeated:
                    go_type = f"[]{go_type}"
                
                go_field_name = to_camel_case(field_name)
                if go_field_name.endswith("Id"):
                    go_field_name = go_field_name[:-2] + "ID"
                
                body_code.append(f"\t{go_field_name} {go_type} `json:\"{field_name},omitempty\"`")
                continue

        # Process Enum Values (Constants)
        if state == "ENUM":
            enum_field_match = enum_field_regex.search(code_part)
            if enum_field_match:
                val_name = enum_field_match.group(1)
                
                if is_first_enum_field:
                    body_code.append(f"\t{val_name} {current_enum_name} = iota")
                    is_first_enum_field = False
                else:
                    body_code.append(f"\t{val_name}")
                continue

        # Process RPC
        if state == "SERVICE":
            rpc_match = rpc_regex.search(code_part)
            if rpc_match:
                method_name = rpc_match.group(1)
                req_type = rpc_match.group(2).replace("stream ", "")
                resp_type = rpc_match.group(3).replace("stream ", "")
                
                logger.debug(f"Processing RPC: {method_name}")
                body_code.append(f"\t{method_name}(ctx context.Context, req *{req_type}) (*{resp_type}, error)")
                continue

    logger.info(f"Parsed {line_count} lines. Generating Go code...")

    go_code = [f"package {package_name}", ""]
    if imports:
        go_code.append("import (")
        for imp in sorted(imports):
            go_code.append(f"\t{imp}")
        go_code.append(")")
        go_code.append("")
    go_code.extend(body_code)
    
    return "\n".join(go_code)

# --- CLI Entry Point ---

@click.command()
@click.argument('input_proto', type=click.Path(exists=True, dir_okay=False))
@click.option('--package', '-p', default='models', help='Go package name for the generated file.', show_default=True)
@click.option('--output', '-o', type=click.Path(writable=True), help='Output file path. If not provided, prints to stdout.')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose debug logging.')
@click.option('--format', '-f', 'should_format', is_flag=True, help='Run gofmt on the generated code.')
@click.option('--log-file', default='converter.log', help='Path to the JSON log file.', show_default=True)
def main(input_proto, package, output, verbose, should_format, log_file):
    """
    Converts a .proto file to a pure Go file with structs, enums, and interfaces.
    
    Designed for REST API migrations, avoiding gRPC dependencies.
    """
    setup_logging(verbose, log_file)
    logger = logging.getLogger("main")

    try:
        go_code = parse_proto_and_generate_go(input_proto, package)
        
        if should_format:
            go_code = run_gofmt(go_code)
        
        if output:
            with open(output, 'w') as f:
                f.write(go_code)
            logger.info(f"Successfully wrote generated code to: [bold green]{output}[/]", extra={"markup": True})
        else:
            # Print to stdout for piping. 
            print(go_code)
            logger.info("Output sent to stdout")

    except Exception as e:
        logger.exception("An unexpected error occurred during conversion.")
        sys.exit(1)

if __name__ == "__main__":
    main()
