import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class PRTGAPI:
    def __init__(self, server_url, username, passhash, verify_ssl=False):
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.passhash = passhash
        self.verify_ssl = verify_ssl
        self.session = requests.Session()

    def build_url(self, endpoint: str) -> str:
        connector = "&" if "?" in endpoint else "?"
        return f"{self.server_url}{endpoint}{connector}username={self.username}&passhash={self.passhash}"

    def test_connection(self):
        try:
            url = self.build_url("/api/table.json?content=sensors&output=json&count=1")
            response = self.session.get(url, verify=self.verify_ssl, timeout=10)
            response.raise_for_status()
            return True, "Conexão com PRTG estabelecida com sucesso."
        except requests.exceptions.RequestException as e:
            return False, f"Erro ao conectar ao PRTG: {str(e)}"

    def get_device_by_name(self, device_name):
        try:
            url = self.build_url("/api/table.json?content=devices&output=json&columns=objid,device,host,group,status")
            response = self.session.get(url, verify=self.verify_ssl)
            response.raise_for_status()
            data = response.json()

            for device in data.get('devices', []):
                if device_name.lower() in device.get('device', '').lower():
                    return device
            return None
        except requests.exceptions.RequestException as e:
            print(f"Erro ao buscar dispositivo: {str(e)}")
            return None

    def get_device_by_core(self, core_name, loja_name):
        try:
            url_groups = self.build_url(f"/api/table.json?content=groups&output=json&columns=objid,name&filter_name=@sub({loja_name})")
            response_groups = self.session.get(url_groups, verify=self.verify_ssl)
            response_groups.raise_for_status()
            data_groups = response_groups.json()

            grupo_loja = next((g for g in data_groups.get('groups', []) if g.get('name', '').lower() == loja_name.lower()), None)

            if not grupo_loja:
                print(f"Grupo '{loja_name}' não encontrado.")
                return None

            grupo_loja_id = grupo_loja['objid']
            url_devices = self.build_url(f"/api/table.json?content=devices&output=json&columns=objid,device,host,group,status,group_raw&filter_parentid={grupo_loja_id}")
            response_devices = self.session.get(url_devices, verify=self.verify_ssl)
            response_devices.raise_for_status()
            dispositivos_data = response_devices.json()

            for device in dispositivos_data.get('devices', []):
                if core_name.lower() in device.get('group', '').lower():
                    return device

            print(f"Nenhum dispositivo encontrado no grupo '{loja_name}' que corresponda ao core '{core_name}'.")
            return None

        except requests.exceptions.RequestException as e:
            print(f"Erro ao buscar dispositivo por grupo/core: {str(e)}")
            return None

    def get_sensors_by_device_id(self, device_id):
        try:
            url = self.build_url(f"/api/table.json?content=sensors&output=json&columns=objid,sensor,status,message_raw,message,lastvalue&id={device_id}")
            response = self.session.get(url, verify=self.verify_ssl)
            response.raise_for_status()
            data = response.json()
            return data.get('sensors', [])
        except requests.exceptions.RequestException as e:
            print(f"Erro ao buscar sensores: {str(e)}")
            return []

    def get_circuit_info(self, loja_name, core_name):
        result = {
            "success": False,
            "message": "",
            "devices_circuits": []
        }

        try:
            url_cores = self.build_url(f"/api/table.json?content=groups&output=json&columns=objid,name&filter_name=@sub({core_name})")
            response_cores = self.session.get(url_cores, verify=self.verify_ssl, timeout=15)
            response_cores.raise_for_status()
            data_cores = response_cores.json()

            grupo_core_obj = next((g for g in data_cores.get('groups', []) if g.get('name', '').strip().lower() == core_name.strip().lower()), None)

            if not grupo_core_obj:
                result["message"] = f"Grupo Core '{core_name}' não encontrado no PRTG."
                return result
            grupo_core_id = grupo_core_obj['objid']

            url_lojas = self.build_url(f"/api/table.json?content=groups&output=json&columns=objid,name,parentid&filter_name=@sub({loja_name})&filter_parentid={grupo_core_id}")
            response_lojas = self.session.get(url_lojas, verify=self.verify_ssl, timeout=15)
            response_lojas.raise_for_status()
            data_lojas = response_lojas.json()

            grupo_loja_obj = next((g for g in data_lojas.get('groups', []) if g.get('name', '').strip().lower() == loja_name.strip().lower()), None)

            if not grupo_loja_obj:
                result["message"] = f"Grupo (Loja) '{loja_name}' não encontrado dentro do Core '{core_name}'."
                return result
            grupo_loja_id = grupo_loja_obj['objid']

            url_devices = self.build_url(f"/api/table.json?content=devices&output=json&columns=objid,device,host,group,status&filter_parentid={grupo_loja_id}")
            response_devices = self.session.get(url_devices, verify=self.verify_ssl, timeout=15)
            response_devices.raise_for_status()
            dispositivos_data = response_devices.json()

            if not dispositivos_data.get('devices', []):
                result["message"] = f"Nenhum dispositivo encontrado no grupo '{loja_name}' (Core: '{core_name}')."
                return result

            found_circuits_for_any_device = False
            for device_info in dispositivos_data.get('devices', []):
                device_id = device_info.get('objid')
                device_name = device_info.get('device', '')

                if not device_name:
                    continue

                sensors_for_device = self.get_sensors_by_device_id(device_id)
                device_circuits_list = []

                for sensor_data in sensors_for_device:
                    sensor_name_norm = sensor_data.get('sensor', '').strip().lower()
                    device_name_norm = device_name.strip().lower()

                    if sensor_name_norm == device_name_norm:
                        circuit = {
                            "id": sensor_data.get('objid'),
                            "name": sensor_data.get('sensor'),
                            "status": sensor_data.get('status'),
                            "message": sensor_data.get('message_raw') or sensor_data.get('message'),
                            "lastvalue": sensor_data.get('lastvalue')
                        }
                        device_circuits_list.append(circuit)
                        found_circuits_for_any_device = True

                if device_circuits_list:
                    result["devices_circuits"].append({
                        "device_id": device_id,
                        "device_name": device_name,
                        "device_host": device_info.get('host'),
                        "device_status": device_info.get('status'),
                        "circuits": device_circuits_list
                    })

            if not found_circuits_for_any_device:
                result["message"] = f"Nenhum sensor correspondente encontrado em '{loja_name}' (Core: '{core_name}')."
            else:
                result["success"] = True
                result["message"] = f"Informações de circuito recuperadas para '{loja_name}' (Core: '{core_name}')."

            return result

        except requests.exceptions.Timeout:
            msg = f"Timeout na API do PRTG ao buscar informações para Loja '{loja_name}', Core '{core_name}'."
            result["message"] = msg
            print(msg)
            return result
        except requests.exceptions.RequestException as e:
            msg = f"Erro na API do PRTG para Cliente '{loja_name}', Core '{core_name}': {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                msg += f" Detalhes: {e.response.status_code} {e.response.text[:200]}"
            result["message"] = msg
            print(msg)
            return result
        except json.JSONDecodeError as e:
            msg = f"Erro ao decodificar JSON da API do PRTG para Cliente '{loja_name}', Core '{core_name}': {str(e)}"
            result["message"] = msg
            print(msg)
            return result
        except Exception as e:
            msg = f"Erro inesperado no PRTG para Cliente '{loja_name}', Core '{core_name}': {str(e)}"
            result["message"] = msg
            print(msg)
            return result
