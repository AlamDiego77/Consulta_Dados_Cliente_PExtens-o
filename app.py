# -*- coding: utf-8 -*-

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox, simpledialog, scrolledtext
from ttkbootstrap import Style
import pandas as pd
import os
import threading
import time # Embora importado, time não é usado diretamente. Pode ser removido se não houver planos futuros.
import queue
import sys
import re

# Importa os módulos locais
from prtg_api import PRTGAPI
from network_tools import NetworkTools

class AppMonitoramentoLojas:
    """Classe principal da aplicação de monitoramento de lojas."""

    def __init__(self, root):
        """
        Inicializa a interface gráfica (GUI) e os componentes da aplicação.

        Args:
            root: O widget raiz do Tkinter (geralmente uma instância de ttk.Window).
        """
        self.root = root
        self.root.title("Monitoramento de Lojas - NOC")
        self.root.geometry("900x650") # Dimensões da janela principal

        # Configuração de estilo para widgets ttkbootstrap
        style = Style()
        style.configure("Amarelo.TButton",
                        background="#FFD700",
                        foreground="black",
                        bordercolor="#2b0d1e",
                        focusthickness=0,
                        font=("Segoe UI", 10))
        style.map("Amarelo.TButton",
                  background=[("active", "#FFD700"), ("pressed", "#e6a914")],
                  bordercolor=[("focus", "#e6a914"), ("hover", "#e6a914")],
                  foreground=[("disabled", "gray")])
        style.configure("Amarelo.TEntry",
                        fieldbackground="#fffde7",
                        bordercolor="#e6a914",
                        foreground="black",
                        focusthickness=1)
        style.map("Amarelo.TEntry",
                  bordercolor=[("focus", "#e6a914"), ("hover", "#e6a914")])

        # Inicialização de variáveis de estado e dados
        self.lojas_df = self.carregar_dados_lojas() # DataFrame com dados das lojas
        self.loja_selecionada = None # Armazena a linha do DataFrame da loja atualmente selecionada
        self.network_tools = NetworkTools() # Instância para ferramentas de rede (ping)
        self.prtg_api = None # Instância da API do PRTG, inicializada após configuração
        self.prtg_configurado = False # Flag para indicar se o PRTG foi configurado
        self.thread_running = False # Flag para indicar se uma operação em thread está em execução
        self.thread_stop = False # Flag para sinalizar a uma thread em execução que ela deve parar

        # --- Layout da Interface Gráfica ---
        main_frame = ttk.Frame(root, padding="15")
        main_frame.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # --- Frame de Consulta de Loja ---
        consulta_frame = ttk.LabelFrame(main_frame, text=" Consultar Loja ", padding="15", bootstyle="success")
        consulta_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        main_frame.columnconfigure(0, weight=1)

        ttk.Label(consulta_frame, text="ID ou Nome da Loja:").grid(row=0, column=0, padx=(0, 10), pady=5, sticky=tk.W)
        self.loja_entry = ttk.Entry(consulta_frame, width=40, style="Amarelo.TEntry")
        self.loja_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        consulta_frame.columnconfigure(1, weight=1)
        self.loja_entry.bind("<Return>", self.buscar_loja_event) # Permite buscar com Enter
        self.loja_entry.focus_set() # Foco inicial no campo de busca

        self.buscar_button = ttk.Button(consulta_frame, text="Buscar", command=self.buscar_loja, style="Amarelo.TButton", width=10)
        self.buscar_button.grid(row=0, column=2, padx=(10, 5), pady=5)
        self.config_prtg_button = ttk.Button(consulta_frame, text="Configurar PRTG", command=self.configurar_prtg, style="Danger", width=15)
        self.config_prtg_button.grid(row=0, column=3, padx=5, pady=5)

        # --- Frame de Informações da Loja ---
        info_frame = ttk.LabelFrame(main_frame, text=" Informações da Loja ", padding="15", bootstyle="success")
        info_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        main_frame.rowconfigure(1, weight=1)

        self.info_text = scrolledtext.ScrolledText(
            info_frame, height=15, width=80, state="disabled", wrap=tk.WORD,
            font=("Consolas", 10), bg="#2b3e50", fg="#ffffff" # Cores para melhor visualização
        )
        self.info_text.grid(row=0, column=0, sticky="nsew")
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(0, weight=1)

        # --- Frame de Ações ---
        self.actions_frame = ttk.Frame(main_frame, padding=(0, 5, 0, 10))
        self.actions_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        self.ver_circuitos_button = ttk.Button(self.actions_frame, text="Ver Circuitos PRTG", command=self.ver_circuitos, state="disabled", bootstyle="info", width=20)
        self.ver_circuitos_button.grid(row=0, column=0, padx=(0, 5), pady=5)

        self.ping_button = ttk.Button(self.actions_frame, text="Ping Links PRTG", command=self.ping_links, state="disabled", bootstyle="success", width=20)
        self.ping_button.grid(row=0, column=1, padx=5, pady=5)
        
        self.ping_vms_button = ttk.Button(self.actions_frame, text="Ping VMs Loja", command=self.ping_vms_action, state="disabled", bootstyle="primary", width=20)
        self.ping_vms_button.grid(row=0, column=2, padx=5, pady=5)

        self.cancelar_button = ttk.Button(self.actions_frame, text="Cancelar Operação", command=self.cancelar_operacao, state="disabled", bootstyle="danger-outline", width=20)
        self.cancelar_button.grid(row=0, column=3, padx=5, pady=5)

        # --- Barra de Status ---
        self.status_var = tk.StringVar()
        self.status_var.set("Pronto")
        self.status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=(10, 5), bootstyle="light")
        self.status_bar.grid(row=3, column=0, sticky="ew")

    def carregar_dados_lojas(self):
        """Carrega os dados das lojas a partir de um arquivo CSV."""
        caminho_csv = os.path.join("data", "lojas.csv") # Assume que o CSV está em uma pasta "data"
        if not os.path.exists(caminho_csv):
            messagebox.showerror("Erro de Dados", f"Arquivo de dados não encontrado: {caminho_csv}")
            return pd.DataFrame() # Retorna DataFrame vazio em caso de erro
        try:
            try:
                # Tenta ler com UTF-8, que é mais comum
                df = pd.read_csv(caminho_csv, dtype={"ID_Loja": str})
            except UnicodeDecodeError:
                # Se falhar, tenta com latin1, comum em sistemas mais antigos ou arquivos do Windows
                df = pd.read_csv(caminho_csv, encoding="latin1", dtype={"ID_Loja": str})
            
            colunas_esperadas = ["ID_Loja", "Nome_Loja", "Core_PRTG", "Cidade", "Estado", "Contato_Gerencia", "Telefone"]
            colunas_presentes = df.columns.tolist()
            colunas_faltando = [col for col in colunas_esperadas if col not in colunas_presentes]
            
            if colunas_faltando:
                 messagebox.showwarning("Aviso de Dados", f"O arquivo {caminho_csv} não contém as colunas esperadas: {', '.join(colunas_faltando)}.")
                 # Adiciona colunas faltantes com valores vazios para evitar KeyErrors posteriores
                 for col in colunas_faltando:
                     df[col] = ""
            
            df = df.fillna("") # Preenche NaNs com strings vazias para consistência
            return df
        except Exception as e:
            messagebox.showerror("Erro ao Carregar Dados", f"Não foi possível ler o arquivo CSV ({caminho_csv}):\n{e}")
            return pd.DataFrame()

    def buscar_loja_event(self, event):
        """Callback para o evento <Return> no campo de busca."""
        self.buscar_loja()

    def buscar_loja(self):
        """Busca uma loja com base no termo inserido pelo usuário."""
        termo_busca = self.loja_entry.get().strip()
        # Não limpar o campo de busca aqui, para o usuário ver o que buscou.
        # self.loja_entry.delete(0, tk.END) 

        self.loja_selecionada = None
        self.atualizar_info_text("") # Limpa informações anteriores
        # Desabilita todos os botões de ação ao iniciar uma nova busca
        self.ver_circuitos_button.config(state="disabled")
        self.ping_button.config(state="disabled")
        self.ping_vms_button.config(state="disabled")

        if not termo_busca:
            messagebox.showwarning("Busca Inválida", "Por favor, insira o ID ou Nome da Loja.")
            return
        
        if self.lojas_df.empty:
            messagebox.showerror("Erro de Dados", "Base de dados de lojas não carregada ou vazia.")
            return

        try:
            # Busca primeiro pelo ID da Loja (correspondência exata)
            if "ID_Loja" in self.lojas_df.columns:
                resultado = self.lojas_df[self.lojas_df["ID_Loja"].astype(str) == termo_busca]
            else:
                resultado = pd.DataFrame() # Garante que resultado é um DataFrame

            # Se não encontrou por ID, busca pelo Nome da Loja (correspondência parcial, case-insensitive)
            if resultado.empty and "Nome_Loja" in self.lojas_df.columns:
                resultado = self.lojas_df[self.lojas_df["Nome_Loja"].str.contains(termo_busca, case=False, na=False)]
        except Exception as e:
            messagebox.showerror("Erro na Busca", f"Ocorreu um erro durante a busca: {e}")
            return

        if resultado.empty:
            self.atualizar_info_text(f"Nenhuma loja encontrada para o termo: \"{termo_busca}\"")
        elif len(resultado) > 1:
            try:
                # Formata a lista de lojas encontradas para exibição
                nomes = "\n".join([f"- {nome} (ID: {id_loja})" 
                                   for nome, id_loja in zip(resultado["Nome_Loja"], resultado["ID_Loja"])])
                self.atualizar_info_text(f"Múltiplas lojas encontradas para \"{termo_busca}\". Refine sua busca.\n\nLojas encontradas:\n{nomes}")
            except KeyError as e:
                 messagebox.showerror("Erro de Dados", f"Coluna '{e}' não encontrada no arquivo CSV. Verifique 'data/lojas.csv'.")
                 self.atualizar_info_text(f"Erro ao listar múltiplas lojas. Coluna '{e}' ausente.")
        else:
            # Loja única encontrada
            self.loja_selecionada = resultado.iloc[0]
            try:
                info = "--- Informações da Loja ---\n"
                info += f"ID:             {self.loja_selecionada.get('ID_Loja', 'N/A')}\n"
                info += f"Nome:           {self.loja_selecionada.get('Nome_Loja', 'N/A')}\n"
                info += f"Core PRTG:      {self.loja_selecionada.get('Core_PRTG', 'N/A')}\n"
                info += f"Cidade:         {self.loja_selecionada.get('Cidade', 'N/A')}\n"
                info += f"Estado:         {self.loja_selecionada.get('Estado', 'N/A')}\n"
                info += f"Contato 1:      {self.loja_selecionada.get('Telefone', 'N/A')}\n"
                # Supondo que pode haver uma coluna Telefone_2, caso contrário, será 'N/A'
                info += f"Contato 2:      {self.loja_selecionada.get('Telefone_2', 'N/A')}\n" 
                info += f"Contato Gerência: {self.loja_selecionada.get('Contato_Gerencia', 'N/A')}\n"
                self.atualizar_info_text(info)
                
                # Habilita o botão Ping VMs Loja, pois não depende do PRTG
                self.ping_vms_button.config(state="normal") 
                
                if self.prtg_configurado:
                    self.ver_circuitos_button.config(state="normal")
                    self.ping_button.config(state="normal")
                else:
                    # Se PRTG não configurado, mantém botões PRTG desabilitados e adiciona aviso
                    self.ver_circuitos_button.config(state="disabled")
                    self.ping_button.config(state="disabled")
                    self.atualizar_info_text(info + "\n\n--- Ações PRTG ---\nAVISO: Configure o PRTG para habilitar as ações relacionadas.")
            except KeyError as e:
                messagebox.showerror("Erro de Dados", f"Coluna '{e}' não encontrada. Verifique 'data/lojas.csv'.")
                self.atualizar_info_text(f"Erro ao exibir detalhes da loja. Coluna '{e}' ausente.")
            except Exception as e:
                 messagebox.showerror("Erro Inesperado", f"Ocorreu um erro ao formatar as informações da loja: {e}")
                 self.atualizar_info_text("Erro inesperado ao exibir detalhes da loja.")

    def configurar_prtg(self):
        """Abre diálogos para o usuário inserir as credenciais do PRTG."""
        server_url = simpledialog.askstring("Configuração PRTG", "URL do servidor PRTG (ex: https://prtg.example.com):", 
                                          initialvalue=getattr(self.prtg_api, "server_url", ""))
        if not server_url: return # Usuário cancelou

        username = simpledialog.askstring("Configuração PRTG", "Nome de usuário PRTG:", 
                                        initialvalue=getattr(self.prtg_api, "username", ""))
        if not username: return # Usuário cancelou

        # Para o passhash, é melhor não mostrar valor inicial se já houver um
        password = simpledialog.askstring("Configuração PRTG", "Senha (Passhash) PRTG:", show="*")
        if password is None: return # Usuário cancelou ou fechou a janela
        
        self.status_var.set("Testando conexão com PRTG...")
        self.root.update_idletasks() # Força atualização da GUI

        try:
            self.prtg_api = PRTGAPI(server_url.strip(), username.strip(), password) # Não passar o passhash diretamente
            success, message = self.prtg_api.test_connection()
            
            if success:
                self.prtg_configurado = True
                messagebox.showinfo("Configuração PRTG", "Conexão com PRTG estabelecida com sucesso!")
                # Se uma loja já estiver selecionada, atualiza o estado dos botões PRTG
                if self.loja_selecionada is not None:
                    self.ver_circuitos_button.config(state="normal")
                    self.ping_button.config(state="normal")
                    # Re-exibe informações da loja para remover o aviso de PRTG não configurado
                    # e garantir que os botões estejam no estado correto.
                    current_id_loja = self.loja_selecionada.get("ID_Loja")
                    if current_id_loja:
                        termo_busca_anterior = self.loja_entry.get() # Salva o que estava no campo de busca
                        self.loja_entry.delete(0, tk.END)
                        self.loja_entry.insert(0, str(current_id_loja))
                        self.buscar_loja() # Isso irá reavaliar e atualizar a UI
                        self.loja_entry.delete(0, tk.END) # Limpa o ID inserido para busca
                        self.loja_entry.insert(0, termo_busca_anterior) # Restaura o termo de busca original
            else:
                self.prtg_configurado = False
                messagebox.showerror("Configuração PRTG", f"Falha na conexão com PRTG: {message}")
        except Exception as e:
            self.prtg_configurado = False
            messagebox.showerror("Erro na Configuração", f"Erro ao tentar configurar o PRTG:\n{e}")
        finally:
            status_final = "PRTG Configurado" if self.prtg_configurado else "Erro na configuração PRTG ou não configurado"
            self.status_var.set(status_final)
    
    def formatar_nome_loja_para_prtg(self, nome_loja_csv):
        """Formata o nome da loja do CSV para o padrão PRTG (ex: 'Loja 10' -> 'LJ010')."""
        if not isinstance(nome_loja_csv, str):
            return str(nome_loja_csv) # Retorna como string se não for
            
        match = re.search(r'\d+', nome_loja_csv)
        if match:
            try:
                numero = int(match.group())
                return f"LJ{numero:03d}" # Formata com 3 dígitos, ex: 10 -> 010
            except ValueError:
                return nome_loja_csv # Retorna original se não conseguir converter número
        return nome_loja_csv # Retorna original se não encontrar números

    def _extrair_numero_loja(self, id_ou_nome_loja):
        """
        Extrai o número da loja do ID_Loja (ex: '10', '010') ou Nome_Loja (ex: 'Loja 10', 'LJ010').
        Usado para construir os IPs das VMs.
        """
        if id_ou_nome_loja is None: return None
        
        # Tenta extrair números de uma string. Ex: "LJ010" -> "010", "Loja 10" -> "10", "10" -> "10"
        match = re.search(r'\d+', str(id_ou_nome_loja)) 
        if match:
            try:
                return int(match.group()) # Converte para inteiro
            except ValueError:
                return None # Falha na conversão
        return None # Nenhum número encontrado

    # --- Métodos de Ação (PRTG e Ping VMs) ---
    def ver_circuitos(self):
        """Inicia a thread para buscar e exibir informações dos circuitos PRTG."""
        if self._verificar_prerequisitos_acao("Ver Circuitos PRTG", require_prtg=True):
            self.status_var.set("Consultando circuitos PRTG...")
            self._preparar_thread_inicio()
            threading.Thread(target=self._thread_ver_circuitos, daemon=True).start()

    def _thread_ver_circuitos(self):
        """(Executado em Thread) Busca informações dos circuitos no PRTG."""
        try:
            nome_loja_csv = self.loja_selecionada.get("Nome_Loja", "N/A")
            nome_loja_prtg = self.formatar_nome_loja_para_prtg(nome_loja_csv)
            core_prtg = self.loja_selecionada.get("Core_PRTG", "N/A")
            
            # Atualiza status na GUI (thread-safe via root.after)
            self.root.after(0, lambda: self.status_var.set(f"Buscando circuitos para {nome_loja_prtg} no Core {core_prtg}..."))
            
            resultado = self.prtg_api.get_circuit_info(nome_loja_prtg, core_prtg)
            
            if self.thread_stop: # Verifica se a operação foi cancelada
                self.root.after(0, lambda: self.status_var.set("Consulta de circuitos cancelada."))
                return
            
            info_display = f"--- Circuitos PRTG para {nome_loja_prtg} (Core: {core_prtg}) ---\n"
            if not resultado.get("success"):
                info_display += f"Erro ao buscar dados do PRTG: {resultado.get("message", "Erro desconhecido")}\n"
            else:
                devices_circuits = resultado.get("devices_circuits", [])
                if not devices_circuits:
                    info_display += "Nenhum dispositivo com circuitos PRTG correspondentes foi encontrado.\n"
                else:
                    for dev_data in devices_circuits:
                        info_display += f"Dispositivo: {dev_data.get('device_name', 'N/A')} "
                        info_display += f"(Host: {dev_data.get('device_host', 'N/A')}, Status: {dev_data.get('device_status', 'N/A')})\n"
                        circuits = dev_data.get("circuits", [])
                        if circuits:
                            for i, c in enumerate(circuits, 1):
                                info_display += f"  {i}. Sensor: {c.get('name', 'N/A')}\n"
                                info_display += f"     Status: {c.get('status', 'N/A')}\n"
                                info_display += f"     Mensagem: {c.get('message', 'N/A')}\n"
                                info_display += f"     Último Valor: {c.get('lastvalue', 'N/A')}\n"
                        else:
                            info_display += "  Nenhum sensor de circuito PRTG encontrado para este dispositivo.\n"
                        info_display += "\n" # Linha em branco entre dispositivos
            
            self.root.after(0, lambda: self.atualizar_info_text(info_display))
            self.root.after(0, lambda: self.status_var.set(f"Circuitos de {nome_loja_prtg} carregados."))

        except Exception as e:
            error_msg = f"Erro inesperado ao consultar circuitos PRTG: {e}"
            self.root.after(0, lambda: messagebox.showerror("Erro na Thread", error_msg))
            self.root.after(0, lambda: self.status_var.set("Erro ao consultar circuitos PRTG."))
        finally:
            self.root.after(0, self._finalizar_thread) # Garante que a UI é reabilitada

    def ping_links(self):
        """Inicia a thread para pingar os links da loja (obtidos do PRTG)."""
        if self._verificar_prerequisitos_acao("Ping Links PRTG", require_prtg=True):
            self.status_var.set("Iniciando ping dos links PRTG...")
            self._preparar_thread_inicio()
            threading.Thread(target=self._thread_ping_links, daemon=True).start()

    def _thread_ping_links(self):
        """(Executado em Thread) Obtém IPs do PRTG e realiza pings."""
        try:
            nome_loja_csv = self.loja_selecionada.get("Nome_Loja", "N/A")
            nome_loja_prtg = self.formatar_nome_loja_para_prtg(nome_loja_csv)
            core_prtg = self.loja_selecionada.get("Core_PRTG", "N/A")
            hosts_para_ping = []

            self.root.after(0, lambda: self.status_var.set(f"Consultando IPs no PRTG para {nome_loja_prtg}..."))
            resultado_api = self.prtg_api.get_circuit_info(nome_loja_prtg, core_prtg)
            
            if self.thread_stop: return

            if resultado_api.get("success") and resultado_api.get("devices_circuits"):
                for dev_data in resultado_api["devices_circuits"]:
                    host_prtg = dev_data.get("device_host")
                    if host_prtg and host_prtg not in hosts_para_ping: # Evita duplicados
                        hosts_para_ping.append(host_prtg)
            
            if not hosts_para_ping:
                # Se não encontrou IPs no PRTG, pergunta ao usuário
                ip_queue = queue.Queue()
                prompt_msg = f"IPs dos links de {nome_loja_prtg} não encontrados no PRTG. \nDigite um IP para ping (ou deixe em branco para cancelar):"
                # A função _ask_ip_and_put precisa ser chamada no thread principal da GUI
                self.root.after(0, lambda: self._ask_ip_and_put(ip_queue, prompt_msg))
                ip_manual = ip_queue.get() # Bloqueia até que o usuário insira algo
                
                if self.thread_stop: return
                if not ip_manual or not ip_manual.strip():
                    self.root.after(0, lambda: self.status_var.set("Ping de links PRTG cancelado pelo usuário."))
                    self.root.after(0, lambda: self.atualizar_info_text("Ping de links PRTG cancelado."))
                    return
                hosts_para_ping.append(ip_manual.strip())

            ping_results_text = f"--- Ping Links PRTG para {nome_loja_prtg} ---\n"
            for host_idx, host in enumerate(hosts_para_ping):
                if self.thread_stop: return
                self.root.after(0, lambda h=host, idx=host_idx, total=len(hosts_para_ping):
                                 self.status_var.set(f"Ping para {h} ({idx+1}/{total})..."))
                result = self.network_tools.ping_host(host)
                ping_results_text += f"\nHost: {host}\n"
                if result.get("success"):
                    ping_results_text += f"  Status: Online, Tempo Médio: {result.get("avg_time", "N/A")} ms, Perda: {result.get("packet_loss", "N/A")} %\n"
                else:
                    ping_results_text += f"  Status: Offline / Erro ({result.get("error", "Desconhecido")})\n"
            
            self.root.after(0, lambda: self.atualizar_info_text(ping_results_text))
            self.root.after(0, lambda: self.status_var.set(f"Ping dos links de {nome_loja_prtg} concluído."))

        except Exception as e:
            error_msg = f"Erro inesperado ao realizar ping dos links PRTG: {e}"
            self.root.after(0, lambda: messagebox.showerror("Erro na Thread", error_msg))
            self.root.after(0, lambda: self.status_var.set("Erro no ping dos links PRTG."))
        finally:
            self.root.after(0, self._finalizar_thread)

    def ping_vms_action(self):
        """Inicia a thread para pingar as VMs da loja selecionada."""
        if self._verificar_prerequisitos_acao("Ping VMs Loja", require_prtg=False): # Não requer PRTG
            # self.status_var.set("Iniciando ping das VMs da loja...") # Agora definido por _preparar_thread_inicio
            self._preparar_thread_inicio("Iniciando ping das VMs da loja...")
            threading.Thread(target=self._thread_ping_vms_loja, daemon=True).start()

    def _thread_ping_vms_loja(self):
        """(Executado em Thread) Gera IPs das VMs e executa o ping."""
        try:
            id_loja = self.loja_selecionada.get("ID_Loja")
            nome_loja_display = self.loja_selecionada.get("Nome_Loja", f"Loja ID {id_loja}")
            
            # Tenta extrair o número da loja primeiro do ID, depois do Nome
            numero_loja = self._extrair_numero_loja(id_loja) 
            if numero_loja is None:
                 nome_loja_csv = self.loja_selecionada.get("Nome_Loja")
                 numero_loja = self._extrair_numero_loja(nome_loja_csv)

            if numero_loja is None:
                msg_erro_num_loja = f"Não foi possível determinar o número da loja '{nome_loja_display}' para gerar os IPs das VMs. Verifique os dados no CSV."
                self.root.after(0, lambda: self.atualizar_info_text(msg_erro_num_loja))
                self.root.after(0, lambda: self.status_var.set("Erro ao obter número da loja para Ping VMs."))
                return

            # Define os IPs das VMs com base no número da loja
            ips_vm = {
                "Gateway": f"192.168.{numero_loja}.1",
                "API": f"192.168.{numero_loja}.2",
                "DB": f"192.168.{numero_loja}.3",
                "Manager": f"192.168.{numero_loja}.4"
            }

            ping_results_text = f"--- Ping host principais para {nome_loja_display} (Loja N° {numero_loja}) ---\n"
            
            for vm_idx, (nome_vm, ip_vm) in enumerate(ips_vm.items()):
                if self.thread_stop: return
                self.root.after(0, lambda n=nome_vm, i=ip_vm, idx=vm_idx, total=len(ips_vm):
                                 self.status_var.set(f"Ping para host {n} ({i}) ({idx+1}/{total})..."))
                result = self.network_tools.ping_host(ip_vm)
                ping_results_text += f"\nHost: {nome_vm} (IP: {ip_vm})\n"
                if result.get("success"):
                    ping_results_text += f"  Status: Online, Tempo Médio: {result.get("avg_time", "N/A")} ms, Perda: {result.get("packet_loss", "N/A")} %\n"
                else:
                    ping_results_text += f"  Status: Offline / Erro ({result.get("error", "Desconhecido")})\n"
            
            self.root.after(0, lambda: self.atualizar_info_text(ping_results_text))
            self.root.after(0, lambda: self.status_var.set(f"Ping das VMs de {nome_loja_display} concluído."))

        except Exception as e:
            error_msg = f"Erro inesperado ao realizar ping das VMs: {e}"
            self.root.after(0, lambda: messagebox.showerror("Erro na Thread", error_msg))
            self.root.after(0, lambda: self.status_var.set("Erro no ping das VMs."))
        finally:
            self.root.after(0, self._finalizar_thread)

    # --- Métodos Auxiliares e de Controle da GUI ---
    def _ask_ip_and_put(self, q, prompt):
        """Pede um IP ao usuário e coloca na fila (usado por _thread_ping_links)."""
        ip = simpledialog.askstring("Entrada Necessária", prompt, parent=self.root)
        q.put(ip if ip is not None else "") # Garante que algo é colocado na fila

    def cancelar_operacao(self):
        """Sinaliza para a thread em execução que ela deve parar."""
        if self.thread_running:
            self.thread_stop = True
            self.status_var.set("Cancelando operação em andamento...")
            # A thread em si deve verificar self.thread_stop e terminar graciosamente.

    def _verificar_prerequisitos_acao(self, nome_acao, require_prtg=False):
        """Verifica se as condições para executar uma ação são atendidas."""
        if self.thread_running:
            messagebox.showwarning("Operação em Andamento", 
                                 "Aguarde a operação atual terminar ou cancele-a antes de iniciar uma nova.",
                                 parent=self.root)
            return False
        if self.loja_selecionada is None:
            messagebox.showwarning("Nenhuma Loja Selecionada", 
                                 "Nenhuma loja está selecionada. Por favor, realize uma busca primeiro.",
                                 parent=self.root)
            return False
        if require_prtg and (not self.prtg_configurado or self.prtg_api is None):
            messagebox.showwarning("PRTG Não Configurado", 
                                 f"A ação '{nome_acao}' requer que o PRTG esteja configurado e conectado.",
                                 parent=self.root)
            return False
        return True
    def _preparar_thread_inicio(self, status_msg):
        """Desabilita botões e prepara a GUI para uma operação em thread."""
        self.thread_running = True
        self.thread_stop = False # Reseta a flag de parada
        self.status_var.set(status_msg) # Define a mensagem de status
        # Desabilita botões que iniciam novas operações
        self.ver_circuitos_button.config(state="disabled")
        self.ping_button.config(state="disabled")
        self.ping_vms_button.config(state="disabled")
        self.buscar_button.config(state="disabled")
        self.config_prtg_button.config(state="disabled") # Desabilita config PRTG durante operação
        self.cancelar_button.config(state="normal") # Habilita o botão de cancelar

    def _finalizar_thread(self):
        """Reabilita botões e atualiza a GUI após uma operação em thread terminar."""
        self.thread_running = False
        # self.thread_stop é resetado em _preparar_thread_inicio
        
        # Reabilita o botão de busca e configuração do PRTG
        self.buscar_button.config(state="normal")
        self.config_prtg_button.config(state="normal")
        self.cancelar_button.config(state="disabled") # Desabilita o botão de cancelar

        # Reabilita botões de ação com base no estado atual
        if self.loja_selecionada is not None:
            self.ping_vms_button.config(state="normal") # Ping VMs sempre habilitado se loja selecionada
            if self.prtg_configurado:
                self.ver_circuitos_button.config(state="normal")
                self.ping_button.config(state="normal")
            else:
                self.ver_circuitos_button.config(state="disabled")
                self.ping_button.config(state="disabled")
        else: # Nenhuma loja selecionada, todos os botões de ação desabilitados
            self.ver_circuitos_button.config(state="disabled")
            self.ping_button.config(state="disabled")
            self.ping_vms_button.config(state="disabled")

        # Atualiza a barra de status, a menos que já mostre um erro ou cancelamento específico
        current_status = self.status_var.get()
        if not any(s in current_status.lower() for s in ["erro", "cancelad", "falha", "não foi possível"]):
            self.status_var.set("Pronto")

    def atualizar_info_text(self, texto):
        """Atualiza o conteúdo da área de texto de informações."""
        try:
            self.info_text.config(state="normal") # Habilita para edição
            self.info_text.delete(1.0, tk.END) # Limpa conteúdo anterior
            self.info_text.insert(tk.END, texto) # Insere novo texto
            self.info_text.config(state="disabled") # Desabilita novamente
        except Exception as e:
            print(f"Erro crítico ao atualizar a área de texto 'info_text': {e}")
            # Tenta exibir uma mensagem de erro na própria caixa de texto, se possível
            try:
                self.info_text.config(state="normal")
                self.info_text.delete(1.0, tk.END)
                self.info_text.insert(tk.END, f"Erro ao exibir informações: {e}")
                self.info_text.config(state="disabled")
            except: 
                pass # Evita loop de erro se a própria caixa de texto estiver com problemas

# --- Bloco de Execução Principal (__main__) ---
if __name__ == "__main__":
    # Verificação e tentativa de instalação de dependências
    dependencias = {
        "pandas": "pandas", 
        "requests": "requests", 
        "ttkbootstrap": "ttkbootstrap"
    }
    faltando = []
    try:
        import importlib
        for nome_modulo_import, nome_pacote_pip in dependencias.items():
            try:
                importlib.import_module(nome_modulo_import)
            except ImportError:
                faltando.append(nome_pacote_pip)
    except ImportError:
        # Caso raro onde o próprio importlib não está disponível (Python muito antigo/quebrado)
        print("Erro crítico: O módulo 'importlib' não foi encontrado. Verifique sua instalação Python.")
        sys.exit(1)

    if faltando:
        print(f"Dependências faltando: {', '.join(faltando)}. Tentando instalar via pip...")
        import subprocess
        try:
            # Tenta instalar as dependências usando o executável Python atual para chamar o pip
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + faltando)
            print("Dependências foram instaladas com sucesso. Por favor, execute o script novamente.")
            sys.exit(0) # Sai para o usuário reexecutar com as dependências carregadas
        except subprocess.CalledProcessError as e_pip:
            print(f"Erro ao instalar dependências via pip: {e_pip}")
            # Tentativa específica para Tkinter no Linux, que às vezes requer python3-tk
            if ("tkinter" in faltando or "ttkbootstrap" in faltando) and sys.platform.startswith("linux"):
                 print("Como Tkinter/ttkbootstrap está faltando no Linux, tentando instalar 'python3-tk' via apt (pode requerer sudo)...")
                 try:
                     # Esses comandos podem precisar de privilégios de superusuário
                     subprocess.check_call(["sudo", "apt-get", "update", "-y"])
                     subprocess.check_call(["sudo", "apt-get", "install", "-y", "python3-tk"])
                     print("'python3-tk' parece ter sido instalado. Por favor, execute o script novamente.")
                     sys.exit(0)
                 except Exception as e_apt:
                     print(f"Falha ao tentar instalar 'python3-tk' via apt: {e_apt}")        
            print("Por favor, instale as dependências manualmente e tente executar o script novamente.")
            sys.exit(1)

    # Cria a janela principal da aplicação com um tema do ttkbootstrap
    root = ttk.Window(themename="cyborg") # Outros temas: "litera", "cosmo", "flatly", "journal", "darkly", etc.
    app = AppMonitoramentoLojas(root)
    root.mainloop() # Inicia o loop de eventos da GUI
