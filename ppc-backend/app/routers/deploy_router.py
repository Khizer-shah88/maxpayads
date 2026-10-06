"""
Auto-deployment endpoint
Allows triggering deployment via HTTP request
"""

from fastapi import APIRouter, HTTPException, Header, Depends
from typing import Optional
import subprocess
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deploy", tags=["Deployment"])


def verify_deploy_token(x_deploy_token: Optional[str] = Header(None)):
    """Verify deployment token for security"""
    # You can set this in environment variable: DEPLOY_TOKEN
    expected_token = os.getenv("DEPLOY_TOKEN", "your-secret-deploy-token-12345")
    
    if not x_deploy_token or x_deploy_token != expected_token:
        raise HTTPException(status_code=403, detail="Invalid deploy token")
    
    return True


@router.post("/reload")
async def trigger_reload(authorized: bool = Depends(verify_deploy_token)):
    """
    Trigger auto-reload of the application
    
    Usage:
    curl -X POST https://your-domain.com/deploy/reload \
         -H "X-Deploy-Token: your-secret-deploy-token-12345"
    """
    try:
        logger.info("Deployment reload triggered via API")
        
        # Try to reload using various methods
        reload_commands = [
            # PM2
            ["pm2", "reload", "ppc-backend"],
            # Systemd (using sudo-less systemctl if configured)
            ["systemctl", "--user", "reload", "ppc-backend"],
            # Touch reload file for ASGI servers
            ["touch", "/tmp/reload.txt"],
        ]
        
        success = False
        method = None
        
        for cmd in reload_commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    success = True
                    method = cmd[0]
                    logger.info(f"Reload successful using {method}")
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        
        if success:
            return {
                "success": True,
                "message": f"Application reloaded successfully using {method}",
                "method": method
            }
        else:
            # If all methods fail, try to restart via os._exit (nuclear option)
            logger.warning("Standard reload methods failed, attempting process restart")
            
            # This will cause the process to exit and supervisor/pm2 will restart it
            import signal
            os.kill(os.getpid(), signal.SIGUSR1)  # Send USR1 signal to trigger reload
            
            return {
                "success": True,
                "message": "Reload signal sent to process",
                "method": "signal"
            }
            
    except Exception as e:
        logger.error(f"Deployment reload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reload failed: {str(e)}")


@router.post("/pull-and-reload")
async def trigger_pull_and_reload(authorized: bool = Depends(verify_deploy_token)):
    """
    Pull latest code from git and reload application
    
    Usage:
    curl -X POST https://your-domain.com/deploy/pull-and-reload \
         -H "X-Deploy-Token: your-secret-deploy-token-12345"
    """
    try:
        logger.info("Git pull and reload triggered via API")
        
        # Get current directory
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Pull latest code
        pull_result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=current_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if pull_result.returncode != 0:
            raise Exception(f"Git pull failed: {pull_result.stderr}")
        
        logger.info(f"Git pull output: {pull_result.stdout}")
        
        # Now reload the application
        reload_response = await trigger_reload(authorized=authorized)
        
        return {
            "success": True,
            "message": "Code updated and application reloaded",
            "git_output": pull_result.stdout,
            "reload": reload_response
        }
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Git pull timed out")
    except Exception as e:
        logger.error(f"Pull and reload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pull and reload failed: {str(e)}")


@router.get("/status")
async def deployment_status(authorized: bool = Depends(verify_deploy_token)):
    """
    Get current deployment status
    """
    try:
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Get current git commit
        commit_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=current_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        # Get current branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=current_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        return {
            "success": True,
            "commit": commit_result.stdout.strip() if commit_result.returncode == 0 else "unknown",
            "branch": branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown",
            "directory": current_dir
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
