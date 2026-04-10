import subprocess
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

class ImapsyncWrapper:
    @staticmethod
    def run_sync(source_email: str, source_password: str, target_email: str, 
                 target_password: str, source_host: str = None) -> Tuple[bool, str]:
        """
        Run imapsync to migrate emails.
        
        Returns:
            Tuple of (success: bool, output: str)
        """
        try:
            # Build imapsync command
            cmd = [
                "imapsync",
                f"--host1={source_host or 'imap.gmail.com'}",
                f"--user1={source_email}",
                f"--password1={source_password}",
                "--ssl1",
                "--host2=localhost",
                f"--user2={target_email}",
                f"--password2={target_password}",
                "--ssl2",
                "--all",
                "--skipheader"
            ]
            
            # Run command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode == 0:
                logger.info(f"imapsync completed successfully for {source_email} -> {target_email}")
                return True, result.stdout
            else:
                logger.error(f"imapsync failed: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            error_msg = "imapsync timed out (exceeded 1 hour)"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"imapsync execution error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    @staticmethod
    def run_sync_with_logging(source_email: str, source_password: str, target_email: str,
                             target_password: str, on_log_callback=None, source_host: str = None) -> Tuple[bool, str]:
        """
        Run imapsync with logging callback for real-time output.
        """
        try:
            cmd = [
                "imapsync",
                f"--host1={source_host or 'imap.gmail.com'}",
                f"--user1={source_email}",
                f"--password1={source_password}",
                "--ssl1",
                "--host2=localhost",
                f"--user2={target_email}",
                f"--password2={target_password}",
                "--ssl2",
                "--all",
                "--skipheader"
            ]
            
            output_lines = []
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Read output line by line
            for line in process.stdout:
                line = line.rstrip()
                output_lines.append(line)
                if on_log_callback:
                    on_log_callback(line)
            
            process.wait(timeout=3600)
            
            if process.returncode == 0:
                full_output = "\n".join(output_lines)
                logger.info(f"imapsync completed successfully for {source_email} -> {target_email}")
                return True, full_output
            else:
                stderr = process.stderr.read() if process.stderr else "Unknown error"
                logger.error(f"imapsync failed: {stderr}")
                return False, stderr
                
        except subprocess.TimeoutExpired:
            process.kill()
            error_msg = "imapsync timed out (exceeded 1 hour)"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"imapsync execution error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
