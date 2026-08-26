import subprocess
import logging
from typing import Callable, Optional, Tuple

CANCELLED = "CANCELLED"

logger = logging.getLogger(__name__)

class ImapsyncWrapper:
    @staticmethod
    def _build_cmd(source_email: str, source_password: str, target_email: str,
                   target_password: str, source_host: str = None, source_port: int = 993,
                   source_ssl: bool = True, target_host: str = "localhost",
                   target_port: int = 993, target_ssl: bool = True,
                   dry_run: bool = False, folders: str = None,
                   maxage_days: int = None, since_date: str = None) -> list:
        """Build the imapsync command."""
        cmd = [
            "imapsync",
            f"--host1={source_host or 'imap.gmail.com'}",
            f"--port1={source_port or 993}",
            f"--user1={source_email}",
            f"--password1={source_password}",
            "--ssl1" if source_ssl else "--nossl1",
            f"--host2={target_host or 'localhost'}",
            f"--port2={target_port or 993}",
            f"--user2={target_email}",
            f"--password2={target_password}",
            "--ssl2" if target_ssl else "--nossl2",
            "--all",
        ]
        if dry_run:
            cmd.append("--dry")
        if folders:
            for folder in [f.strip() for f in folders.split(",") if f.strip()]:
                cmd.append(f"--include={folder}")
        if maxage_days:
            cmd.append(f"--maxage={int(maxage_days)}")
        if since_date:
            cmd.append(f"--since={since_date}")
        return cmd

    @staticmethod
    def run_sync(source_email: str, source_password: str, target_email: str,
                 target_password: str, source_host: str = None, source_port: int = 993,
                 source_ssl: bool = True, target_host: str = "localhost",
                 target_port: int = 993, target_ssl: bool = True,
                 dry_run: bool = False, folders: str = None,
                 maxage_days: int = None, since_date: str = None) -> Tuple[bool, str]:
        """
        Run imapsync to migrate emails.

        Returns:
            Tuple of (success: bool, output: str)
        """
        try:
            cmd = ImapsyncWrapper._build_cmd(
                source_email, source_password, target_email, target_password,
                source_host=source_host, source_port=source_port, source_ssl=source_ssl,
                target_host=target_host, target_port=target_port, target_ssl=target_ssl,
                dry_run=dry_run, folders=folders, maxage_days=maxage_days,
                since_date=since_date,
            )
            
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
                             target_password: str, on_log_callback=None, source_host: str = None,
                             source_port: int = 993, source_ssl: bool = True,
                             target_host: str = "localhost", target_port: int = 993,
                             target_ssl: bool = True, dry_run: bool = False,
                             folders: str = None, maxage_days: int = None,
                             since_date: str = None,
                             should_cancel: Optional[Callable[[], bool]] = None) -> Tuple[bool, str]:
        """
        Run imapsync with logging callback for real-time output.

        If `should_cancel` is provided, it's checked after each output line;
        when it returns True the subprocess is killed and this returns
        (False, CANCELLED) instead of treating it as a failure.
        """
        try:
            cmd = ImapsyncWrapper._build_cmd(
                source_email, source_password, target_email, target_password,
                source_host=source_host, source_port=source_port, source_ssl=source_ssl,
                target_host=target_host, target_port=target_port, target_ssl=target_ssl,
                dry_run=dry_run, folders=folders, maxage_days=maxage_days,
                since_date=since_date,
            )

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
                if should_cancel and should_cancel():
                    process.kill()
                    process.wait(timeout=10)
                    logger.info(f"imapsync cancelled for {source_email} -> {target_email}")
                    return False, CANCELLED

            process.wait(timeout=3600)
            
            if process.returncode == 0:
                full_output = "\n".join(output_lines)
                logger.info(f"imapsync completed successfully for {source_email} -> {target_email}")
                return True, full_output
            else:
                stderr = process.stderr.read() if process.stderr else ""
                detail = stderr or "\n".join(output_lines) or "Unknown error"
                logger.error(f"imapsync failed: {detail}")
                return False, detail
                
        except subprocess.TimeoutExpired:
            process.kill()
            error_msg = "imapsync timed out (exceeded 1 hour)"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"imapsync execution error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
