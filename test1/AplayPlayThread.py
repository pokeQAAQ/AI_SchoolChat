"""
Audio playback thread using aplay from alsa-utils.
Requires: pacman -S alsa-utils (or equivalent package manager)
"""
import os
import signal
import subprocess
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker


class AplayPlayThread(QThread):
    """Audio playback thread using aplay command (alsa-utils)"""
    finished_signal = Signal()
    stopped_signal = Signal()

    def __init__(self, audio_path, device=None):
        super().__init__()
        self.audio_path = audio_path
        self.device = device  # e.g., "hw:0,0" or None for default
        self.mutex = QMutex()
        self._stop_requested = False
        self._process = None

    def run(self):
        """Play audio using aplay"""
        try:
            # Check if file exists
            if not self.audio_path or not os.path.exists(self.audio_path):
                raise FileNotFoundError(f"Audio file not found: {self.audio_path}")

            if os.path.getsize(self.audio_path) == 0:
                raise ValueError(f"Audio file is empty: {self.audio_path}")

            # Build aplay command
            cmd = ['aplay', '-q']  # -q for quiet mode

            # Add device if specified
            if self.device:
                cmd.extend(['-D', self.device])

            # Determine file format and add appropriate parameters
            if self.audio_path.endswith('.wav'):
                cmd.extend(['-t', 'wav'])
            else:
                # Assume raw PCM format (16-bit, 16kHz, mono)
                cmd.extend(['-t', 'raw', '-f', 'S16_LE', '-r', '16000', '-c', '1'])

            cmd.append(self.audio_path)

            print(f"[AplayPlayThread] Running: {' '.join(cmd)}")

            # Start aplay process
            with QMutexLocker(self.mutex):
                if self._stop_requested:
                    return
                self._process = subprocess.Popen(cmd, 
                                               stdout=subprocess.DEVNULL, 
                                               stderr=subprocess.PIPE)

            # Wait for completion or stop request
            while True:
                # Check if stop was requested
                with QMutexLocker(self.mutex):
                    if self._stop_requested:
                        break

                # Check if process finished
                if self._process.poll() is not None:
                    break

                # Short sleep to avoid busy waiting
                self.msleep(50)

            # Get process result
            return_code = self._process.poll()
            
            if return_code == 0:
                print(f"[AplayPlayThread] Playback completed successfully")
            elif return_code is None:
                # Process was stopped
                print(f"[AplayPlayThread] Playback stopped")
            else:
                # Process had an error
                stderr_output = self._process.stderr.read().decode('utf-8', errors='replace')
                print(f"[AplayPlayThread] aplay error (code {return_code}): {stderr_output}")

        except Exception as e:
            print(f"[AplayPlayThread] Error: {str(e)}")
        finally:
            self._cleanup()
            
            # Emit appropriate signal
            with QMutexLocker(self.mutex):
                if self._stop_requested:
                    self.stopped_signal.emit()
                else:
                    self.finished_signal.emit()

    def stop(self):
        """Stop audio playback"""
        with QMutexLocker(self.mutex):
            self._stop_requested = True
            
            if self._process and self._process.poll() is None:
                try:
                    # Send SIGTERM to gracefully stop aplay
                    self._process.terminate()
                    
                    # Wait a bit for graceful termination
                    try:
                        self._process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't stop gracefully
                        self._process.kill()
                        self._process.wait()
                        
                except Exception as e:
                    print(f"[AplayPlayThread] Error stopping process: {e}")

        # Wait for thread to finish
        if self.isRunning():
            self.wait(2000)  # Wait up to 2 seconds

    def _cleanup(self):
        """Clean up resources"""
        with QMutexLocker(self.mutex):
            if self._process:
                try:
                    if self._process.poll() is None:
                        self._process.terminate()
                        try:
                            self._process.wait(timeout=0.5)
                        except subprocess.TimeoutExpired:
                            self._process.kill()
                            self._process.wait()
                except Exception as e:
                    print(f"[AplayPlayThread] Cleanup error: {e}")
                finally:
                    self._process = None