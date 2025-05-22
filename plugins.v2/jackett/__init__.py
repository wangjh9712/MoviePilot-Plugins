import base64
import json
from typing import Dict, Any, List, Optional, Tuple
import time
import requests
import urllib.parse

from app.plugins import _PluginBase
from app.log import logger

class Jackett(_PluginBase):
    plugin_name = "Jackett 配置日志输出器"
    plugin_desc = "从 Jackett 获取索引器，格式化为“自定义索引站点”插件配置（无分类，尝试无encoding），并输出到 MoviePilot 日志中。"
    plugin_icon = "https://raw.githubusercontent.com/Jackett/Jackett/master/src/Jackett.Common/Content/favicon.ico"
    plugin_version = "3.7"
    plugin_author = "jason (modified by AI)"
    author_url = "https://github.com/xj-bear"
    plugin_config_prefix = "jackett_"
    plugin_order = 22
    user_level = 2

    _enabled = False
    _host = None
    _api_key = None
    _password = None

    def init_plugin(self, config: dict = None) -> None:
        logger.info(f"【{self.plugin_name} ({self.__class__.__name__})】正在初始化插件...")
        if not config: logger.warn(f"【{self.plugin_name} ({self.__class__.__name__})】配置为空...")
        self._enabled = config.get("enabled", False) if config else False
        self._host = config.get("host") if config else None
        self._api_key = config.get("api_key") if config else None
        self._password = config.get("password") if config else None
        logger.info(f"【{self.plugin_name} ({self.__class__.__name__})】初始化完成。Enabled: {self._enabled}, Host: {'SET' if self._host else 'NOT SET'}, API Key: {'SET' if self._api_key else 'NOT SET'}")
        if self._enabled and self._host and self._api_key:
            logger.info(f"【{self.plugin_name}】插件已启用且配置齐全，尝试记录Jackett配置...")
            self.log_jackett_indexer_configs()
        elif self._enabled:
            logger.warn(f"【{self.plugin_name}】插件已启用，但Jackett Host或API Key未配置。")

    def _fetch_jackett_indexers(self) -> List[Dict[str, Any]]:
        logger.info(f"【{self.plugin_name}】'_fetch_jackett_indexers' CALLED. Host: {self._host}, API Key: {'[SET]' if self._api_key else '[NOT SET]'}")
        if not self._host or not self._api_key: return []
        host = self._host.rstrip('/')
        max_retries, retry_interval = 2, 3
        api_headers = {"User-Agent": f"MoviePilot-Plugin-{self.__class__.__name__}/{self.plugin_version}", "X-Api-Key": self._api_key, "Accept": "application/json, text/javascript, */*; q=0.01"}
        with requests.Session() as session:
            if self._password:
                login_url, login_submission_url = f"{host}/UI/Login", f"{host}/UI/Dashboard"
                try: session.get(login_url, verify=False, timeout=10)
                except requests.exceptions.RequestException: pass
                login_post_headers = {"User-Agent": api_headers["User-Agent"], "Content-Type": "application/x-www-form-urlencoded", "Referer": login_url}
                try: session.post(login_submission_url, data={"password": self._password}, headers=login_post_headers, verify=False, timeout=15, allow_redirects=True)
                except requests.exceptions.RequestException: pass
            else:
                try: session.get(f"{host}/", headers={"User-Agent": api_headers["User-Agent"]}, verify=False, timeout=10, allow_redirects=True)
                except requests.exceptions.RequestException: pass
            indexer_query_url, current_try = f"{host}/api/v2.0/indexers?configured=true", 1
            while current_try <= max_retries:
                logger.info(f"【{self.plugin_name}】(Session) 请求Jackett索引器 (尝试 {current_try}/{max_retries}): {indexer_query_url}")
                try:
                    current_session_headers = session.headers.copy(); current_session_headers.update(api_headers)
                    response = session.get(indexer_query_url, headers=current_session_headers, verify=False, timeout=20)
                    logger.info(f"【{self.plugin_name}】API响应状态: {response.status_code}")
                    if response.status_code == 200 and 'application/json' in response.headers.get('Content-Type','').lower():
                        indexers = response.json(); return indexers if isinstance(indexers, list) else []
                    # Simplified error logging for brevity here
                except requests.exceptions.RequestException as e: logger.warn(f"【{self.plugin_name}】请求Jackett异常 (尝试 {current_try}): {e}")
                except Exception as e: logger.error(f"【{self.plugin_name}】处理Jackett响应未知错误 (尝试 {current_try}): {e}", exc_info=True)
                if current_try < max_retries: time.sleep(retry_interval)
                current_try += 1
        logger.warn(f"【{self.plugin_name}】无法获取Jackett索引器列表。")
        return []

    def _format_indexer_for_moviepilot(self, jackett_indexer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            indexer_id_from_jackett = jackett_indexer.get("id", "") 
            indexer_name_from_jackett = jackett_indexer.get("name", "")
            if not indexer_id_from_jackett or not indexer_name_from_jackett: return None

            moviepilot_internal_id = f"jackett_{indexer_id_from_jackett.lower().replace('-', '_')}" 
            actual_jackett_host = self._host.rstrip('/')
            
            mp_indexer_config_json = {
                "id": moviepilot_internal_id,
                "name": f"[Jackett] {indexer_name_from_jackett}",
                "domain": actual_jackett_host, 
                "url": actual_jackett_host,    
                # "encoding": "UTF-8", # Removed/Commented out
                "public": True, "proxy": True, 
                "language": jackett_indexer.get("language", "en-US"),
                "search": {
                    "paths": [{"path": f"/api/v2.0/indexers/{indexer_id_from_jackett}/results/torznab", "method": "get"}],
                    "params": { "t": "search", "q": "{keyword}", "apikey": self._api_key }
                },
                "torrents": {
                    "list": {"selector": "item"},
                    "fields": {
                        "title": {"selector": "title"}, "details": {"selector": "guid"}, 
                        "download": {"selector": "link"}, "size": {"selector": "size"}, 
                        "date_added": {"selector": "pubDate", "optional": True},
                        "seeders": {"selector": "torznab:attr[name=seeders]", "filters": [{"name": "re", "args": ["(\\d+)", 1]}], "default": "0"},
                        "leechers": {"selector": "torznab:attr[name=peers]", "filters": [{"name": "re", "args": ["(\\d+)", 1]}], "default": "0"}, 
                        "downloadvolumefactor": {"case": {"*": 0}}, "uploadvolumefactor": {"case": {"*": 1}}
                    }
                }
            }
            logger.debug(f"【{self.plugin_name}】格式化MP配置JSON for '{moviepilot_internal_id}' (无分类, 无encoding)")
            return mp_indexer_config_json
        except Exception as e:
            logger.error(f"【{self.plugin_name}】格式化索引器 '{jackett_indexer.get('name', 'N/A')}' 失败: {e}", exc_info=True)
            return None

    def log_jackett_indexer_configs(self):
        logger.info(f"【{self.plugin_name}】开始生成Jackett索引器配置字符串...")
        if not self._host: logger.error(f"【{self.plugin_name}】Jackett host 未配置!"); return
        parsed_jackett_url = urllib.parse.urlparse(self._host)
        domain_key_for_custom_indexer_plugin = parsed_jackett_url.netloc 
        if not parsed_jackett_url.scheme or not domain_key_for_custom_indexer_plugin:
            logger.error(f"【{self.plugin_name}】解析Jackett Host失败 ('{self._host}'). 请确保格式为 http(s)://hostname:port"); return
        logger.info(f"【{self.plugin_name}】将使用 '{domain_key_for_custom_indexer_plugin}' 作为自定义索引器的主机标识(IP:Port)。")
        raw_jackett_indexers = self._fetch_jackett_indexers()
        if not raw_jackett_indexers: logger.warn(f"【{self.plugin_name}】未从Jackett获取到索引器。"); return
        all_config_lines, output_count = [], 0
        for raw_indexer in raw_jackett_indexers:
            indexer_name = raw_indexer.get("name", "N/A")
            mp_config_json_object = self._format_indexer_for_moviepilot(raw_indexer)
            if mp_config_json_object:
                try:
                    final_domain_key_for_pipe = domain_key_for_custom_indexer_plugin
                    json_str_for_encoding = json.dumps(mp_config_json_object, ensure_ascii=False, indent=None)
                    base64_encoded_json = base64.b64encode(json_str_for_encoding.encode('utf-8')).decode('utf-8')
                    custom_config_line = f"{final_domain_key_for_pipe}|{base64_encoded_json}"
                    all_config_lines.append(custom_config_line)
                    output_count +=1
                except Exception as e: logger.error(f"【{self.plugin_name}】为索引器 '{indexer_name}' 生成Base64配置时出错: {e}", exc_info=True)
            else: logger.warn(f"【{self.plugin_name}】未能格式化索引器 '{indexer_name}' 的MoviePilot配置。")
        if all_config_lines:
            logger.info(f"【{self.plugin_name}】为 {output_count} 个Jackett索引器生成的“自定义索引站点”配置:")
            logger.info(f"MOVIEPILOT_CUSTOM_INDEXER_CONFIG_BLOCK_START")
            for line in all_config_lines: logger.info(line)
            logger.info(f"MOVIEPILOT_CUSTOM_INDEXER_CONFIG_BLOCK_END")
            logger.info(f"【{self.plugin_name}】共 {output_count} 条配置已记录。")
        else: logger.warn(f"【{self.plugin_name}】未能成功生成任何配置字符串。")
        logger.info(f"【{self.plugin_name}】Jackett索引器配置记录过程结束。")

    def get_form(self) -> Tuple[List[dict], dict]:
        return [
            {'component': 'VAlert', 'props': {'type': 'info', 'text': '启用并配置Jackett服务器信息后，插件会自动获取Jackett中的索引器，并将其“自定义索引站点”配置字符串输出到MoviePilot的日志中。您需要从日志中复制这些配置。点击下方按钮可手动触发一次日志记录。', 'class': 'mb-4'}},
            {'component': 'VSwitch', 'props': {'model': 'enabled', 'label': '启用插件'}},
            {'component': 'VTextField', 'props': {'model': 'host', 'label': 'Jackett地址', 'placeholder': 'http://localhost:9117', 'hint': '请输入Jackett的完整地址，包括http或https前缀和端口号。'}},
            {'component': 'VTextField', 'props': {'model': 'api_key', 'label': 'API Key', 'type': 'password', 'placeholder': 'Jackett管理界面右上角的API Key'}},
            {'component': 'VTextField', 'props': {'model': 'password', 'label': 'Jackett管理密码 (可选)', 'type': 'password', 'placeholder': 'Jackett管理界面配置的Admin password，如未配置可为空。'}},
            {
                'component': 'VBtn',
                'props': {'color': 'secondary', 'class': 'mt-4', 'block': True,},
                'text': '手动记录Jackett索引器配置到日志',
                'events': [{'name': 'click', 'value': "() => { this.$axios.get('/api/v1/plugin/Jackett/jackett/trigger_log_configs').then(res => { if(res.data.code === 0) { this.$toast.success(res.data.message || '操作成功，请查看日志。'); } else { this.$toast.error(res.data.message || '操作失败，请查看日志。');} }).catch(err => this.$toast.error('触发日志记录请求失败: ' + (err.response?.data?.message || err.message))); }"}]
            }
        ], {"enabled": False, "host": "", "api_key": "", "password": ""}

    def get_state(self) -> bool: return self._enabled
    def stop_service(self) -> None: logger.info(f"【{self.plugin_name} ({self.__class__.__name__})】插件服务已停止。")
    def get_page(self) -> Optional[List[dict]]: return None 
    def get_api(self) -> List[dict]:
        return [{"path": "/jackett/trigger_log_configs", "endpoint": self.api_trigger_log_configs, "methods": ["GET"], "summary": "手动触发记录Jackett索引器配置到日志", "description": "调用此API会使插件重新获取Jackett索引器并将其配置输出到日志。"}]
    def api_trigger_log_configs(self):
        logger.info(f"【{self.plugin_name}】收到手动触发记录Jackett配置的API请求。")
        if not self._enabled: return {"code": 1, "message": "插件未启用，请先在设置中启用。"}
        if not self._host or not self._api_key: return {"code": 1, "message": "Jackett Host或API Key未配置，请在插件设置中配置。"}
        self.log_jackett_indexer_configs()
        return {"code": 0, "message": "已尝试记录Jackett索引器配置到MoviePilot日志，请查看日志获取结果。"}