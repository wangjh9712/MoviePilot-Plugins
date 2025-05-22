import base64
import json
from typing import Dict, Any, List, Optional, Tuple
import time
import requests
import urllib.parse # For parsing self._host

from app.plugins import _PluginBase
from app.log import logger

class Jackett(_PluginBase):
    plugin_name = "Jackett 配置日志输出器"
    plugin_desc = "从 Jackett 获取索引器，格式化为“自定义索引站点”插件配置，并输出到 MoviePilot 日志中。"
    plugin_icon = "https://raw.githubusercontent.com/Jackett/Jackett/master/src/Jackett.Common/Content/favicon.ico"
    plugin_version = "3.6"
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
        if not config: logger.warn(f"【{self.plugin_name} ({self.__class__.__name__})】配置为空，插件功能可能受限。")
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
        # Using the previously successful _fetch_jackett_indexers method
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
                    # Simplified error logging for brevity here, full logging was in previous versions
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

            # This is the unique ID for MoviePilot's internal management (e.g., jackett_1337x)
            # It will also be the "id" field *inside* the JSON config.
            moviepilot_internal_id = f"jackett_{indexer_id_from_jackett.lower().replace('-', '_')}" 
            
            # This is the full base URL of the Jackett server, including scheme, host, and port
            # e.g., "http://192.168.31.44:9117"
            actual_jackett_base_url = self._host.rstrip('/')
            
            # The 'domain' and 'url' fields *inside* the JSON will point to the actual Jackett server base URL.
            # The CustomIndexer plugin might ignore these if it uses the part before '|' as the host.
            
            mp_indexer_config_json = {
                "id": moviepilot_internal_id, # Unique ID within MoviePilot for this indexer
                "name": f"[Jackett] {indexer_name_from_jackett}",
                "domain": actual_jackett_base_url, # Actual Jackett server (e.g., http://192.168.31.44:9117)
                "url": actual_jackett_base_url,    # Actual Jackett server
                "encoding": "UTF-8", "public": True, "proxy": True, 
                "language": jackett_indexer.get("language", "en-US"),
                # No "category" field, search params also have no "cat"
                "search": {
                    "paths": [{
                        # This path is relative to "domain"/"url" above.
                        "path": f"/api/v2.0/indexers/{indexer_id_from_jackett}/results/torznab", 
                        "method": "get"
                    }],
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
            logger.debug(f"【{self.plugin_name}】格式化MP配置JSON for '{moviepilot_internal_id}' (无分类, URL: {actual_jackett_base_url})")
            return mp_indexer_config_json
        except Exception as e:
            logger.error(f"【{self.plugin_name}】格式化索引器 '{jackett_indexer.get('name', 'N/A')}' 失败: {e}", exc_info=True)
            return None

    def log_jackett_indexer_configs(self):
        logger.info(f"【{self.plugin_name}】开始生成Jackett索引器配置字符串...")
        if not self._host: logger.error(f"【{self.plugin_name}】Jackett host 未配置!"); return
        
        # Parse the user-configured Jackett host to get scheme, hostname and port
        # self._host is like "http://192.168.31.44:9117"
        parsed_jackett_url = urllib.parse.urlparse(self._host)
        jackett_scheme = parsed_jackett_url.scheme # "http" or "https"
        # jackett_netloc will be "192.168.31.44:9117"
        # This will be used as the 'domain_key' for CustomIndexer
        domain_key_for_custom_indexer_plugin = parsed_jackett_url.netloc 
        
        if not jackett_scheme or not domain_key_for_custom_indexer_plugin:
            logger.error(f"【{self.plugin_name}】解析Jackett Host失败 ('{self._host}'). 请确保格式为 http(s)://hostname:port")
            return

        logger.info(f"【{self.plugin_name}】将使用 '{domain_key_for_custom_indexer_plugin}' 作为自定义索引器的主机标识(IP:Port)。")

        raw_jackett_indexers = self._fetch_jackett_indexers()
        if not raw_jackett_indexers: logger.warn(f"【{self.plugin_name}】未从Jackett获取到索引器。"); return

        all_config_lines, output_count = [], 0
        for raw_indexer in raw_jackett_indexers:
            indexer_name = raw_indexer.get("name", "N/A")
            mp_config_json_object = self._format_indexer_for_moviepilot(raw_indexer)
            if mp_config_json_object:
                try:
                    # The JSON's internal "id" (e.g., "jackett_1337x") is NOT used as the domain_key here.
                    # We use the parsed actual_jackett_host_and_port as the domain_key.
                    # This means CustomIndexer will see: "192.168.31.44:9117|Base64JSON..."
                    # where Base64JSON contains "id":"jackett_1337x", "url":"http://192.168.31.44:9117", etc.
                    
                    json_str_for_encoding = json.dumps(mp_config_json_object, ensure_ascii=False, indent=None)
                    base64_encoded_json = base64.b64encode(json_str_for_encoding.encode('utf-8')).decode('utf-8')
                    
                    # The part before "|" is what CustomIndexer uses as the "host" for requests.
                    # So, it must be "hostname:port" or just "hostname" (if default port 80/443).
                    # The JSON payload contains the full scheme://hostname:port/path for the search.
                    # HOWEVER, given your previous test "他不会使用 url字段", this implies
                    # CustomIndexer *only* uses the part before "|" to construct the *entire base URL*.
                    # This is tricky. Let's try two options for domain_part, controlled by a flag for now.

                    # Option 1 (Preferred, if CustomIndexer is somewhat smart):
                    # Use a unique ID for CustomIndexer's key, and rely on JSON's "url"
                    # domain_part = mp_config_json_object['id'] # e.g. "jackett_1337x"
                    
                    # Option 2 (If CustomIndexer is dumb and uses key as full host:port):
                    # The key itself is "host:port". The JSON's "url" field also contains "scheme://host:port".
                    # The JSON's "search.paths[0].path" is then appended to this.
                    
                    # Based on your test "他不会使用 url字段" and "直接访问了http://jackett_1337x//",
                    # it seems CustomIndexer takes the `domain_key` and prepends "http://" and appends search path.
                    # It does NOT seem to take scheme or port from `domain_key` if it's just an identifier.
                    # But if `domain_key` IS "host:port", it might use it.
                    
                    # Let's stick to the "domain_key IS host:port" strategy as it's the most direct
                    # if CustomIndexer uses the domain_key as the literal authority part of the URL.
                    
                    # The 'domain_key' passed to CustomIndexer.add_indexer(domain_key, json_config)
                    # This 'domain_key' will be used by MP to build the URL.
                    # It should be 'hostname:port' if non-standard port, or just 'hostname'
                    # The scheme (http/https) will be prepended by MP, likely based on some default or JSON field.
                    
                    # Let's make the domain_key for CustomIndexer plugin the "netloc" part (host:port)
                    # And ensure the JSON "search.paths.path" is the *full path* not relative to scheme/host.
                    # NO, this is wrong. The 'path' in JSON is always relative to 'url' in JSON.
                    
                    # The problem is that CustomIndexer uses its 'domain_key' to construct the base URL,
                    # ignoring 'url' in the JSON for the *base*.
                    # So, 'domain_key' must be resolvable AND have the correct port.

                    # If your host plugin makes "jackett_1337x" resolve to "192.168.31.44",
                    # and MP defaults to port 80 for "http://jackett_1337x", that's the issue.

                    # The JSON config we provide to CustomIndexer:
                    # Its "url" field (e.g. "http://192.168.31.44:9117") should ideally be used.
                    # If it's ignored, and only the "domain_key" (e.g. "jackett_1337x") is used,
                    # AND if MoviePilot forms URL like "http://" + domain_key + search_path_from_json,
                    # then the port is missing.

                    # Let's assume CustomIndexer takes the 'domain_key' and uses it as follows:
                    # http_scheme + domain_key + json_config['search']['paths'][0]['path']
                    # The http_scheme might come from json_config['url'] or default to http.
                    
                    # To ensure correct port, the 'domain_key' itself must contain 'hostname:port'
                    # IF MoviePilot's HTTP client correctly parses 'hostname:port' from the host part of a URL.
                    
                    # Let `domain_part_for_custom_indexer_plugin_line` be what goes before "|".
                    # This MUST be what MP tries to connect to.
                    # From your test, if this is "jackett_1337x", MP connects to "jackett_1337x:80" (after your host plugin).
                    
                    # The most robust solution is that the JSON config's "url" field should be fully respected by CustomIndexer.
                    # Since it's not, we use the workaround:
                    # The "domain_key" for CustomIndexer will be the actual "hostname:port" from your Jackett URL.
                    # Your host plugin is NO LONGER NEEDED if we do this.
                    
                    final_domain_key_for_pipe = domain_key_for_custom_indexer_plugin # This is "192.168.31.44:9117"
                    
                    # The JSON *inside* the base64 should still have its own "id" for internal MP reference if needed
                    # and its "url" should be the full "http://192.168.31.44:9117"
                    # mp_config_json_object already has this structure.

                    custom_config_line = f"{final_domain_key_for_pipe}|{base64_encoded_json}"
                    all_config_lines.append(custom_config_line)
                    output_count +=1
                except Exception as e:
                    logger.error(f"【{self.plugin_name}】为索引器 '{indexer_name}' 生成Base64配置时出错: {e}", exc_info=True)
            else:
                logger.warn(f"【{self.plugin_name}】未能格式化索引器 '{indexer_name}' 的MoviePilot配置。")

        if all_config_lines:
            logger.info(f"【{self.plugin_name}】为 {output_count} 个Jackett索引器生成的“自定义索引站点”配置:")
            logger.info(f"MOVIEPILOT_CUSTOM_INDEXER_CONFIG_BLOCK_START")
            for line in all_config_lines: logger.info(line)
            logger.info(f"MOVIEPILOT_CUSTOM_INDEXER_CONFIG_BLOCK_END")
            logger.info(f"【{self.plugin_name}】共 {output_count} 条配置已记录。")
        else: logger.warn(f"【{self.plugin_name}】未能成功生成任何配置字符串。")
        logger.info(f"【{self.plugin_name}】Jackett索引器配置记录过程结束。")

    # --- Standard plugin methods ---
    def get_form(self) -> Tuple[List[dict], dict]:
        return [
            {'component': 'VAlert', 'props': {'type': 'info', 'text': '启用并配置Jackett服务器信息后，插件会自动获取Jackett中的索引器，并将其“自定义索引站点”配置字符串输出到MoviePilot的日志中。您需要从日志中复制这些配置。点击下方按钮可手动触发一次日志记录。', 'class': 'mb-4'}},
            {'component': 'VSwitch', 'props': {'model': 'enabled', 'label': '启用插件'}},
            {'component': 'VTextField', 'props': {'model': 'host', 'label': 'Jackett地址', 'placeholder': 'http://localhost:9117', 'hint': '请输入Jackett的完整地址，包括http或https前缀和端口号。'}}, # Emphasize port
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