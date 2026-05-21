"""
excel.py

The 'Processing' organ of the Agent.
Handles detailed data manipulation via pandas.
Revenue-Grade: Deterministic, Persistent, Measurable.
"""
import os
import pandas as pd
from typing import Dict, Any, List, Optional
from ..tool import Tool

class ExcelTool(Tool):
    name = "excel_processing"
    description = "Process Excel files. Commands: load_workbook, append_to_master, compute_summary, generate_report."
    
    def run(self, action: str, **kwargs) -> Any:
        if action == "load_workbook":
            return self.load_workbook(**kwargs)
        elif action == "append_to_master":
            return self.append_to_master(**kwargs)
        elif action == "compute_summary":
            return self.compute_summary(**kwargs)
        elif action == "generate_report":
            return self.generate_report(**kwargs)
        else:
            return f"Error: Unknown excel action '{action}'"
            
    def load_workbook(self, path: str) -> Dict[str, Any]:
        """Loads data into memory to verify it exists and is valid."""
        try:
            if not os.path.exists(path):
                return {"error": f"File not found: {path}"}
            
            df = pd.read_excel(path)
            return {
                "rows": len(df),
                "columns": list(df.columns),
                "preview": df.head(3).to_dict(orient="records")
            }
        except Exception as e:
            return {"error": f"Failed to load workbook: {str(e)}"}
            
    def append_to_master(self, source_path: str, master_path: str) -> Dict[str, Any]:
        """Appends data from source to master."""
        try:
            if not os.path.exists(source_path):
                return {"error": f"Source file not found: {source_path}"}
                
            source_df = pd.read_excel(source_path)
            
            if os.path.exists(master_path):
                master_df = pd.read_excel(master_path)
                # Check for duplicates? For now, blind append.
                # Actually, persistent state implies we should maybe add a 'Processed' date?
                # MVP: Just append.
                new_master = pd.concat([master_df, source_df], ignore_index=True)
                rows_added = len(source_df)
            else:
                # Create new master
                new_master = source_df
                rows_added = len(source_df)
                # Ensure directory exists
                os.makedirs(os.path.dirname(master_path), exist_ok=True)
                
            new_master.to_excel(master_path, index=False)
            
            return {
                "rows_added": rows_added,
                "new_total_rows": len(new_master),
                "status": "success"
            }
        except Exception as e:
            return {"error": f"Append failed: {str(e)}"}
            
    def compute_summary(self, path: str) -> Dict[str, Any]:
        """Computes analytics from the dataset."""
        try:
            if not os.path.exists(path):
                return {"error": f"File not found: {path}"}
                
            df = pd.read_excel(path)
            
            # Heuristic Calculation for 'Revenue' workflow
            if "Revenue" in df.columns:
                total_revenue = float(df["Revenue"].sum())
            else:
                total_revenue = 0.0
                
            # Top Product
            top_product = "N/A"
            if "Product" in df.columns:
                top_product = df["Product"].mode()[0] if not df["Product"].empty else "N/A"
                
            return {
                "total_rows": len(df),
                "total_revenue": total_revenue,
                "top_product": top_product,
                "status": "success"
            }
        except Exception as e:
            return {"error": f"Summary failed: {str(e)}"}
            
    def generate_report(self, output_path: str, summary: Dict[str, Any] = None, master_path: str = None) -> Dict[str, Any]:
        """Writes human-readable report."""
        try:
            # If summary not provided, compute it from master_path
            if summary is None and master_path:
                summary = self.compute_summary(master_path)
                if "error" in summary:
                    return summary
            
            if summary is None:
                return {"error": "generate_report requires 'summary' dict or 'master_path'"}

            # Ensure dir exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, "w") as f:
                f.write(f"DAILY SALES REPORT\n")
                f.write(f"==================\n")
                f.write(f"Total Orders: {summary.get('total_rows', 0)}\n")
                f.write(f"Total Revenue: ${summary.get('total_revenue', 0)}\n")
                f.write(f"Top Product: {summary.get('top_product', 'N/A')}\n")
                f.write(f"==================\n")
                f.write(f"Generated by Agent.\n")
                
            return {
                "report_path": output_path,
                "status": "success"
            }
        except Exception as e:
            return {"error": f"Report generation failed: {str(e)}"}
