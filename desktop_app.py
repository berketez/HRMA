#!/usr/bin/env python3
"""
HRMA Desktop Application
Standalone executable launcher for the Hybrid Rocket Motor Analysis tool
"""

import os
import sys
import threading
import webbrowser
import time
import socket
from pathlib import Path

# Add current directory to path for imports
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

try:
    from app import app
    import tkinter as tk
    from tkinter import messagebox, ttk
    from PIL import Image, ImageTk
except ImportError as e:
    print(f"Missing required packages: {e}")
    print("Please install required packages:")
    print("pip install flask flask-cors numpy plotly trimesh pillow")
    sys.exit(1)

class HRMADesktopApp:
    def __init__(self):
        self.flask_thread = None
        self.port = self.find_free_port()
        self.root = None
        self.setup_gui()
    
    def find_free_port(self):
        """Find a free port for Flask app"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    def setup_gui(self):
        """Setup the desktop GUI"""
        self.root = tk.Tk()
        self.root.title("UZAYTEK - Hybrid Rocket Motor Analysis")
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        
        # Center window
        self.center_window()
        
        # Configure style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Logo/Title
        title_label = ttk.Label(
            main_frame, 
            text="UZAYTEK\nHybrid Rocket Motor Analysis", 
            font=("Arial", 16, "bold"),
            justify=tk.CENTER
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=20)
        
        # Status label
        self.status_label = ttk.Label(
            main_frame, 
            text="Ready to launch", 
            font=("Arial", 10)
        )
        self.status_label.grid(row=1, column=0, columnspan=2, pady=10)
        
        # Progress bar
        self.progress = ttk.Progressbar(
            main_frame, 
            mode='indeterminate',
            length=300
        )
        self.progress.grid(row=2, column=0, columnspan=2, pady=10)
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)
        
        # Launch button
        self.launch_btn = ttk.Button(
            button_frame, 
            text="Launch Application", 
            command=self.launch_app,
            width=20
        )
        self.launch_btn.grid(row=0, column=0, padx=5)
        
        # Open browser button
        self.browser_btn = ttk.Button(
            button_frame, 
            text="Open Browser", 
            command=self.open_browser,
            state=tk.DISABLED,
            width=15
        )
        self.browser_btn.grid(row=0, column=1, padx=5)
        
        # Info frame
        info_frame = ttk.LabelFrame(main_frame, text="Information", padding="10")
        info_frame.grid(row=4, column=0, columnspan=2, pady=20, sticky=(tk.W, tk.E))
        
        info_text = f"""
        Version: 1.0
        Port: {self.port}
        Status: Offline
        
        This application will start the HRMA web server
        and open it in your default browser.
        """
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT)
        info_label.grid(row=0, column=0)
        
        # Exit button
        exit_btn = ttk.Button(
            main_frame, 
            text="Exit", 
            command=self.on_closing,
            width=10
        )
        exit_btn.grid(row=5, column=0, columnspan=2, pady=10)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def center_window(self):
        """Center the window on screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def launch_app(self):
        """Launch the Flask application"""
        try:
            self.launch_btn.config(state=tk.DISABLED)
            self.status_label.config(text="Starting server...")
            self.progress.start()
            
            # Start Flask in a separate thread
            self.flask_thread = threading.Thread(target=self.run_flask, daemon=True)
            self.flask_thread.start()
            
            # Wait a moment for server to start
            self.root.after(2000, self.check_server_and_open)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start application: {str(e)}")
            self.reset_ui()
    
    def run_flask(self):
        """Run the Flask application"""
        try:
            app.run(
                host='127.0.0.1',
                port=self.port,
                debug=False,
                use_reloader=False,
                threaded=True
            )
        except Exception as e:
            print(f"Flask error: {e}")
    
    def check_server_and_open(self):
        """Check if server is running and open browser"""
        try:
            # Try to connect to the server
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', self.port))
            sock.close()
            
            if result == 0:
                # Server is running
                self.progress.stop()
                self.status_label.config(text=f"Server running on port {self.port}")
                self.browser_btn.config(state=tk.NORMAL)
                self.open_browser()
            else:
                # Server not ready yet, check again
                self.root.after(1000, self.check_server_and_open)
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to server: {str(e)}")
            self.reset_ui()
    
    def open_browser(self):
        """Open the application in default browser"""
        url = f"http://127.0.0.1:{self.port}"
        webbrowser.open(url)
        
        # Minimize the desktop app window
        self.root.iconify()
    
    def reset_ui(self):
        """Reset UI to initial state"""
        self.progress.stop()
        self.launch_btn.config(state=tk.NORMAL)
        self.browser_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Ready to launch")
    
    def on_closing(self):
        """Handle application closing"""
        if messagebox.askokcancel("Quit", "Do you want to quit the application?"):
            if self.flask_thread and self.flask_thread.is_alive():
                # Flask server will be killed when main process exits
                pass
            self.root.destroy()
            sys.exit(0)
    
    def run(self):
        """Run the desktop application"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.on_closing()

def main():
    """Main function"""
    print("Starting UZAYTEK HRMA Desktop Application...")
    
    # Check if running as frozen executable
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_path = sys._MEIPASS
        os.chdir(base_path)
    else:
        # Running as script
        base_path = os.path.dirname(os.path.abspath(__file__))
        os.chdir(base_path)
    
    # Start the desktop app
    app_instance = HRMADesktopApp()
    app_instance.run()

if __name__ == "__main__":
    main()