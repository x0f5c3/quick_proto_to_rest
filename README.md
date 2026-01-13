# **Proto to Pure Go Converter (REST Migration)**

This tool quickly generates Go structs and interfaces from .proto files without pulling in gRPC dependencies (google.golang.org/grpc or google.golang.org/protobuf).  
It is designed for projects migrating from gRPC to REST that want to keep using Protobuf definitions as the source of truth for models but require clean Go structures with JSON tags.

## **Prerequisites**

* **Python 3.10+**
* **uv** (Python package manager) - highly recommended for easy execution.

## **Usage**

Since the script uses PEP 723 metadata, you can run it directly with uv without manually installing dependencies.

### **Basic Usage (Print to stdout)**

uv run main.py example.proto

### **Save to File**

uv run main.py example.proto --output models.go --package mypkg

### **Full Options**

Usage: main.py \[OPTIONS] INPUT\_PROTO

Converts a .proto file to a pure Go file with structs and interfaces.

Options:  
-p, --package TEXT   Go package name for the generated file.  \[default: models]  
-o, --output PATH    Output file path. If not provided, prints to stdout.  
-v, --verbose        Enable verbose debug logging.  
--log-file TEXT      Path to the JSON log file.  \[default: converter.log]  
--help               Show this message and exit.

## **Features**

1. **UUID Support:** If a field comment contains UUID (e.g., string id = 1; // user UUID), it is converted to uuid.UUID in Go.
2. **Structured Logging:**

   * **Console:** Pretty colored logs (via rich) printed to stderr.
   * **File:** JSON structured logs saved to converter.log (useful for CI/CD or debugging).

3. **Clean Output:** No gRPC metadata, just pure Go structs and interfaces.

## **Output Example**

From example.proto:  
message User {  
string id = 1; // user UUID  
}

Generates:  
package models

import (  
"\[github.com/google/uuid](https://github.com/google/uuid)"  
)

type User struct {  
ID uuid.UUID `json:"id,omitempty"`  
}

