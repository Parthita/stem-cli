"""
Entry point for running stem watcher as a subprocess.
"""

import sys
import argparse
from pathlib import Path

def main():
    """Main entry point for watcher subprocess."""
    parser = argparse.ArgumentParser(description='Stem filesystem watcher')
    parser.add_argument('--path', required=True, help='Directory to watch')
    parser.add_argument('--timeout', type=int, default=3, help='Idle timeout in seconds')
    
    args = parser.parse_args()
    
    # Import here to avoid circular imports
    from .watcher import start_watching
    
    try:
        # Change to the target directory
        import os
        os.chdir(args.path)
        
        # Start watching
        start_watching(args.path, args.timeout)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Watcher error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()