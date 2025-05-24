import subprocess
import platform
import threading
import queue
import re
import socket
import time

class NetworkTools:
    def __init__(self):
        self.ping_results = {}
        self.ping_queue = queue.Queue()
        self.ping_threads = []
        self.max_threads = 5
        
    def _decode_output(self, output_bytes):
        if not output_bytes:
            return ""
        encodings_to_try = ["cp850", "latin-1", "utf-8"]
        for encoding in encodings_to_try:
            try:
                return output_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return output_bytes.decode("utf-8", errors="replace")

    def ping_host(self, host, count=4, timeout=2):
        result = {
            "host": host,
            "success": False,
            "min_time": None,
            "avg_time": None,
            "max_time": None,
            "packet_loss": 100,
            "error": None
        }
        
        system = platform.system().lower()
        
        # Inicializa stdout e stderr para evitar UnboundLocalError
        stdout_bytes, stderr_bytes = b"", b""
        stdout, stderr = "", ""
        process = None # Inicializa process para o bloco finally

        try:
            if system == "windows":
                cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), host]
            else:
                cmd = ["ping", "-c", str(count), "-W", str(timeout), host]
            
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                creationflags=subprocess.CREATE_NO_WINDOW if system == "windows" else 0
            )
            stdout_bytes, stderr_bytes = process.communicate(timeout=timeout + 2) # Adiciona um timeout para communicate

            stdout = self._decode_output(stdout_bytes)
            stderr = self._decode_output(stderr_bytes)

            current_packet_loss = 100

            if stdout:
                if system == "windows":
                    loss_match_pt = re.search(r"Perdidos\s*=\s*\d+\s*\((\d+)%\s*de\s*perda\)", stdout, re.IGNORECASE)
                    if loss_match_pt:
                        current_packet_loss = int(loss_match_pt.group(1))
                    else:
                        loss_match_en = re.search(r"Lost\s*=\s*\d+\s*\((\d+)%\s*loss\)", stdout, re.IGNORECASE) 
                        if not loss_match_en:
                            loss_match_en = re.search(r"(\d+)%\s*loss", stdout, re.IGNORECASE)
                        if loss_match_en:
                            current_packet_loss = int(loss_match_en.group(1))
                    result["packet_loss"] = current_packet_loss

                    times_match_pt = re.search(r"Mínimo\s*=\s*(\d+)ms,\s*Máximo\s*=\s*(\d+)ms,\s*Média\s*=\s*(\d+)ms", stdout, re.IGNORECASE)
                    if times_match_pt:
                        result["min_time"] = int(times_match_pt.group(1))
                        result["max_time"] = int(times_match_pt.group(2))
                        result["avg_time"] = int(times_match_pt.group(3))
                    else:
                        times_match_en = re.search(r"Minimum\s*=\s*(\d+)ms,\s*Maximum\s*=\s*(\d+)ms,\s*Average\s*=\s*(\d+)ms", stdout, re.IGNORECASE)
                        if times_match_en:
                            result["min_time"] = int(times_match_en.group(1))
                            result["max_time"] = int(times_match_en.group(2))
                            result["avg_time"] = int(times_match_en.group(3))
                
                else:  # Linux/Unix/MacOS
                    loss_match = re.search(r"(\d+)%\s*packet\s*loss", stdout, re.IGNORECASE)
                    if loss_match:
                        current_packet_loss = int(loss_match.group(1))
                    result["packet_loss"] = current_packet_loss
                    
                    times_match = re.search(r"min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)", stdout)
                    if times_match:
                        result["min_time"] = float(times_match.group(1))
                        result["avg_time"] = float(times_match.group(2))
                        result["max_time"] = float(times_match.group(3))
            
            # Usa process.returncode APÓS communicate() ter finalizado
            return_code = process.returncode
            if return_code == 0 and result["packet_loss"] < 100:
                result["success"] = True
            elif return_code == 0 and result["packet_loss"] == 100:
                result["success"] = False
                if not result["error"] and stdout:
                    first_line_stdout = stdout.splitlines()[0].strip() if stdout.splitlines() else ""
                    if "Esgotado o tempo limite" in first_line_stdout or "Request timed out" in first_line_stdout:
                        result["error"] = first_line_stdout
                    else:
                        result["error"] = "Host respondeu ao comando ping, mas com 100% de perda de pacotes."
                elif not result["error"]:
                     result["error"] = "Host respondeu ao comando ping, mas com 100% de perda de pacotes."
                result["min_time"] = None
                result["avg_time"] = None
                result["max_time"] = None
            else:
                result["success"] = False
                error_message = f"Comando ping falhou (código: {return_code})"
                if stderr:
                    error_message += f" - Erro: {stderr.strip()}"
                elif stdout: 
                    error_message += f" - Saída: {stdout.strip()}"
                result["error"] = error_message

        except FileNotFoundError:
            result["success"] = False
            result["error"] = "Comando 'ping' não encontrado. Verifique a instalação e o PATH."
        except subprocess.TimeoutExpired: # Captura TimeoutExpired de communicate()
            result["success"] = False
            result["error"] = f"Comando ping excedeu o tempo limite ({timeout+2}s)."
            if process: process.kill() # Garante que o processo é morto
            # stdout_bytes, stderr_bytes podem ter sido parcialmente preenchidos ou não
            stdout = self._decode_output(stdout_bytes)
            stderr = self._decode_output(stderr_bytes)
            if stderr: result["error"] += f" Erro parcial: {stderr.strip()}"
            if stdout: result["error"] += f" Saída parcial: {stdout.strip()}"
        except Exception as e:
            result["success"] = False
            result["error"] = f"Erro inesperado ao executar ping: {str(e)} (stdout: {stdout[:100]}, stderr: {stderr[:100]})"
        
        return result
    
    def _ping_worker(self):
        while True:
            try:
                item = self.ping_queue.get(block=True, timeout=1) 
                if item is None: 
                    self.ping_queue.task_done()
                    break
                
                host, count, timeout, key = item
                ping_result_data = self.ping_host(host, count, timeout)
                self.ping_results[key] = ping_result_data
                self.ping_queue.task_done()
            except queue.Empty:
                break 
            except Exception as e:
                if 'item' in locals() and item is not None: 
                    host_on_error, _, _, key_on_error = item
                    self.ping_results[key_on_error] = {
                        "host": host_on_error,
                        "success": False,
                        "error": f"Erro interno no worker: {str(e)}",
                        "packet_loss": 100,
                        "min_time": None, "avg_time": None, "max_time": None
                    }
                if hasattr(self.ping_queue, 'task_done'): 
                    try:
                        self.ping_queue.task_done() 
                    except ValueError:
                        pass
    
    def ping_multiple_hosts(self, hosts, count=4, timeout=2):
        self.ping_results = {} 
        
        while not self.ping_queue.empty():
            try:
                self.ping_queue.get_nowait()
            except queue.Empty:
                break
            finally:
                try:
                    self.ping_queue.task_done()
                except ValueError:
                    pass

        keys_for_results = []
        for host_item in hosts:
            if isinstance(host_item, tuple):
                host, key = host_item
            else:
                host = host_item
                key = f"{host}_{int(time.time())}_{threading.get_ident()}"
            keys_for_results.append(key) 
            self.ping_queue.put((host, count, timeout, key))
        
        self.ping_threads = []
        num_threads_to_start = min(self.max_threads, len(hosts))
        for _ in range(num_threads_to_start):
            thread = threading.Thread(target=self._ping_worker)
            thread.daemon = True 
            thread.start()
            self.ping_threads.append(thread)
        
        self.ping_queue.join()
        
        for _ in range(len(self.ping_threads)):
            self.ping_queue.put(None)
        
        for thread in self.ping_threads:
            thread.join()
        
        final_results = {k: self.ping_results[k] for k in keys_for_results if k in self.ping_results}
        return final_results

    def resolve_hostname(self, hostname):
        try:
            return socket.gethostbyname(hostname)
        except socket.gaierror:
            return None
    
    def check_port(self, host, port, timeout=2):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result_code = sock.connect_ex((host, port))
            sock.close()
            return result_code == 0
        except Exception:
            return False

if __name__ == "__main__":
    nt = NetworkTools()
    
    print("--- Testando google.com (real) ---")
    result_google = nt.ping_host("google.com", count=2)
    print(f"Resultado para google.com: {result_google}")
    
    print("\n--- Testando um IP local que responde (ex: gateway, substitua se necessário) ---")
    # result_local_online = nt.ping_host("192.168.1.1", count=2) # Substitua pelo seu IP de gateway
    # print(f"Resultado para IP local online: {result_local_online}")

    print("\n--- Testando um IP local provavelmente offline (ex: 192.168.254.254) ---")
    result_offline = nt.ping_host("192.168.254.254", count=2, timeout=1)
    print(f"Resultado para 192.168.254.254: {result_offline}")

    print("\n--- Testando um IP não roteável (ex: 10.255.255.1) que deve ter 100% de perda ---")
    result_loss = nt.ping_host("10.255.255.1", count=2, timeout=1)
    print(f"Resultado para 10.255.255.1: {result_loss}")

    print("\n--- Testando múltiplos hosts ---")
    hosts_to_test = ["google.com", "facebook.com", "192.168.254.253", "kernel.org"]
    multiple_results = nt.ping_multiple_hosts(hosts_to_test, count=2, timeout=1)
    for host_key, res in multiple_results.items():
        print(f"Resultado para {res['host']}: {res}")
