import base64
import json
from typing import Dict, Any, List, Optional, Tuple
import time
import requests

from app.plugins import _PluginBase
from app.log import logger

class Jackett(_PluginBase):
    """
    Jackett 索引器配置生成并输出到日志的插件
    """
    plugin_name = "Jackett 配置日志输出器"
    plugin_desc = "从 Jackett 获取索引器，格式化为“自定义索引站点”插件配置，并输出到 MoviePilot 日志中。"
    plugin_icon = "https://raw.githubusercontent.com/Jackett/Jackett/master/src/Jackett.Common/Content/favicon.ico"
    plugin_version = "3.2" # Incremented version
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
        if not config:
            logger.warn(f"【{self.plugin_name} ({self.__class__.__name__})】配置为空，插件功能可能受限。")

        self._enabled = config.get("enabled", False) if config else False
        self._host = config.get("host") if config else None
        self._api_key = config.get("api_key") if config else None
        self._password = config.get("password") if config else None
        
        logger.info(f"【{self.plugin_name} ({self.__class__.__name__})】初始化完成。Enabled: {self._enabled}, Host: {'SET' if self._host else 'NOT SET'}, API Key: {'SET' if self._api_key else 'NOT SET'}")

        if self._enabled and self._host and self._api_key:
            logger.info(f"【{self.plugin_name}】插件已启用且配置齐全，尝试获取并记录Jackett索引器配置...")
            self.log_jackett_indexer_configs()
        elif self._enabled:
            logger.warn(f"【{self.plugin_name}】插件已启用，但Jackett Host或API Key未配置。请在插件设置中配置。")

    def _fetch_jackett_indexers(self) -> List[Dict[str, Any]]:
        logger.info(f"【{self.plugin_name}】'_fetch_jackett_indexers' CALLED. Host: {self._host}, API Key: {'[SET]' if self._api_key else '[NOT SET]'}")
        if not self._host or not self._api_key:
            logger.error(f"【{self.plugin_name}】Jackett Host 或 API Key 未配置，无法获取索引器。")
            return []
        
        host = self._host.rstrip('/')
        max_retries = 2 
        retry_interval = 3 
            
        api_headers = {
            "User-Agent": f"MoviePilot-Plugin-{self.__class__.__name__}/{self.plugin_version}",
            "X-Api-Key": self._api_key,
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }
        logger.debug(f"【{self.plugin_name}】API 请求头 (不含 Content-Type for GET): {api_headers}")

        with requests.Session() as session:
            if self._password:
                login_url = f"{host}/UI/Login" 
                try:
                    logger.info(f"【{self.plugin_name}】尝试GET登录页面: {login_url}")
                    session.get(login_url, verify=False, timeout=10) 
                    logger.info(f"【{self.plugin_name}】GET登录页面完成。当前Cookies: {session.cookies.get_dict()}")
                except requests.exceptions.RequestException as e:
                    logger.warn(f"【{self.plugin_name}】GET登录页面失败: {e}")

                login_submission_url = f"{host}/UI/Dashboard" # Jackett's form often posts to dashboard
                login_post_headers = {
                    "User-Agent": api_headers["User-Agent"],
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": login_url 
                }
                try:
                    logger.info(f"【{self.plugin_name}】尝试POST密码到: {login_submission_url}")
                    login_res = session.post(login_submission_url, data={"password": self._password}, headers=login_post_headers, verify=False, timeout=15, allow_redirects=True)
                    logger.info(f"【{self.plugin_name}】密码登录POST响应状态: {login_res.status_code}. URL после POST: {login_res.url}")
                    logger.info(f"【{self.plugin_name}】密码登录后Cookies: {session.cookies.get_dict()}")
                    if "UI/Login" in login_res.url:
                        logger.warn(f"【{self.plugin_name}】密码登录后似乎仍停留在登录页，登录可能未成功。")
                    else:
                        logger.info(f"【{self.plugin_name}】密码登录POST似乎已完成。")
                except requests.exceptions.RequestException as e:
                    logger.error(f"【{self.plugin_name}】密码登录请求失败: {e}")
            else:
                warm_up_url = f"{host}/" 
                try:
                    logger.info(f"【{self.plugin_name}】执行预热请求到: {warm_up_url}")
                    session.get(warm_up_url, headers={"User-Agent": api_headers["User-Agent"]}, verify=False, timeout=10, allow_redirects=True)
                    logger.info(f"【{self.plugin_name}】预热请求完成。当前Cookies: {session.cookies.get_dict()}")
                except requests.exceptions.RequestException as e:
                    logger.warn(f"【{self.plugin_name}】预热请求失败: {e}")

            indexer_query_url = f"{host}/api/v2.0/indexers?configured=true"
            current_try = 1
            while current_try <= max_retries:
                logger.info(f"【{self.plugin_name}】(使用Session) 请求Jackett索引器列表 (尝试 {current_try}/{max_retries}): {indexer_query_url}")
                try:
                    current_session_headers = session.headers.copy()
                    current_session_headers.update(api_headers)      
                    logger.debug(f"【{self.plugin_name}】发送到API的最终请求头 (含 session cookies): {current_session_headers}")
                    response = session.get(indexer_query_url, headers=current_session_headers, verify=False, timeout=20)
                    logger.info(f"【{self.plugin_name}】收到API响应状态: {response.status_code}")
                    if response.status_code == 200:
                        content_type = response.headers.get('Content-Type', '').lower()
                        if 'application/json' in content_type:
                            indexers = response.json()
                            if indexers and isinstance(indexers, list):
                                logger.info(f"【{self.plugin_name}】成功从Jackett获取到 {len(indexers)} 个索引器 (JSON)。")
                                return indexers
                            else: 
                                logger.info(f"【{self.plugin_name}】从Jackett获取的索引器列表为空 (JSON)。")
                                return [] 
                        else:
                            logger.error(f"【{self.plugin_name}】Jackett API响应Content-Type不是JSON: '{content_type}'. 响应码200但内容非预期。")
                            logger.error(f"【{self.plugin_name}】Jackett响应内容 (前500字符): {response.text[:500]}...")
                    elif response.status_code == 302:
                        location = response.headers.get('Location', 'N/A')
                        logger.warn(f"【{self.plugin_name}】Jackett API请求被重定向 (302) 到: {location}.")
                    elif response.status_code in [401, 403]:
                        logger.error(f"【{self.plugin_name}】Jackett API认证或授权失败 (HTTP {response.status_code})。请检查API Key。")
                        return [] 
                    else:
                        logger.warn(f"【{self.plugin_name}】从Jackett API获取索引器列表失败: HTTP {response.status_code}. 内容 (前200): {response.text[:200]}")
                except requests.exceptions.Timeout:
                    logger.warn(f"【{self.plugin_name}】请求Jackett API超时 (尝试 {current_try}/{max_retries}).")
                except requests.exceptions.RequestException as e:
                    logger.error(f"【{self.plugin_name}】请求Jackett API网络异常 (尝试 {current_try}/{max_retries}): {e}")
                except Exception as e: 
                    logger.error(f"【{self.plugin_name}】请求Jackett API时发生未知错误 (尝试 {current_try}/{max_retries}): {e}", exc_info=True)
                if current_try < max_retries:
                    logger.info(f"【{self.plugin_name}】将在 {retry_interval} 秒后重试API请求...")
                    time.sleep(retry_interval)
                current_try += 1
        logger.warn(f"【{self.plugin_name}】经过所有尝试后，未能成功从Jackett API获取索引器列表。")
        return []

    def _format_indexer_for_moviepilot(self, jackett_indexer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            indexer_id_from_jackett = jackett_indexer.get("id", "") 
            indexer_name_from_jackett = jackett_indexer.get("name", "")
            if not indexer_id_from_jackett or not indexer_name_from_jackett:
                logger.warn(f"【{self.plugin_name}】Jackett索引器数据不完整 (缺少ID或名称): {jackett_indexer}")
                return None

            moviepilot_internal_id = f"jackett_{indexer_id_from_jackett.lower().replace('-', '_')}" 
            actual_jackett_host = self._host.rstrip('/')

            # Define a list of categories this site supports, for MoviePilot to use.
            # These IDs are standard Torznab category IDs. Use strings as per reference.
            site_categories = [
                {"id": "2000", "name": "Movies - General"}, # More generic name for UI
                {"id": "2030", "name": "Movies/SD"},
                {"id": "2040", "name": "Movies/HD"},
                {"id": "2045", "name": "Movies/UHD"},
                {"id": "2060", "name": "Movies/3D"},
                # You can add more specific movie categories from Torznab spec if needed
                # e.g., {"id": "2010", "name": "Movies/Foreign"}, etc.

                {"id": "5000", "name": "TV - General"}, # More generic name for UI
                {"id": "5030", "name": "TV/SD"},
                {"id": "5040", "name": "TV/HD"},
                # Add more TV categories if needed
                # e.g., {"id": "5070", "name": "TV/Anime"} (but check if this specific indexer supports it well)
            ]
            # For a more dynamic approach, you could parse jackett_indexer.get("caps", [])
            # and map them to a predefined set of MoviePilot-friendly category names.
            # But for now, a fixed list is simpler to start with.

            mp_indexer_config_json = {
                "id": moviepilot_internal_id,
                "name": f"[Jackett] {indexer_name_from_jackett}",
                "domain": actual_jackett_host, 
                "url": actual_jackett_host,    
                "encoding": "UTF-8",
                "public": True, 
                "proxy": True, 
                "language": "zh_CN", 
                "category": site_categories, # Use the flat list of categories
                "search": {
                    "paths": [
                        {
                            "path": f"/api/v2.0/indexers/{indexer_id_from_jackett}/results/torznab", 
                            "method": "get"
                        }
                    ],
                    "params": { 
                        "t": "search",
                        "q": "{keyword}",
                        "cat": "{cate_id}", # Use {cate_id} - MoviePilot should replace this
                                           # with the 'id' from the 'category' list above,
                                           # based on user's selection in MoviePilot site settings.
                        "apikey": self._api_key
                    }
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
            logger.debug(f"【{self.plugin_name}】格式化MoviePilot索引器配置JSON完成 for '{moviepilot_internal_id}'")
            return mp_indexer_config_json
        except Exception as e:
            logger.error(f"【{self.plugin_name}】格式化索引器 '{jackett_indexer.get('name', 'N/A')}' 失败: {e}", exc_info=True)
            return None

    def log_jackett_indexer_configs(self):
        logger.info(f"【{self.plugin_name}】开始获取Jackett索引器以生成配置字符串...")
        raw_jackett_indexers = self._fetch_jackett_indexers()

        if not raw_jackett_indexers:
            logger.warn(f"【{self.plugin_name}】未能从Jackett获取任何索引器，无法生成配置。请检查连接和Jackett设置。")
            return

        logger.info(f"【{self.plugin_name}】成功获取 {len(raw_jackett_indexers)} 个原始索引器。开始格式化并记录配置...")
        
        all_config_lines = []
        output_count = 0

        for raw_indexer in raw_jackett_indexers:
            indexer_name = raw_indexer.get("name", "N/A")
            logger.debug(f"【{self.plugin_name}】正在处理Jackett索引器: {indexer_name}")
            
            mp_config_json_object = self._format_indexer_for_moviepilot(raw_indexer)
            
            if mp_config_json_object:
                try:
                    domain_part_for_custom_indexer = mp_config_json_object['id']
                    json_str_for_encoding = json.dumps(mp_config_json_object, ensure_ascii=False, indent=None)
                    base64_encoded_json = base64.b64encode(json_str_for_encoding.encode('utf-8')).decode('utf-8')
                    
                    custom_config_line = f"{domain_part_for_custom_indexer}|{base64_encoded_json}"
                    all_config_lines.append(custom_config_line)
                    output_count +=1
                    logger.debug(f"【{self.plugin_name}】为 '{indexer_name}' 生成配置行: {custom_config_line[:50]}...")
                except Exception as e:
                    logger.error(f"【{self.plugin_name}】为索引器 '{indexer_name}' 生成Base64配置时出错: {e}", exc_info=True)
            else:
                logger.warn(f"【{self.plugin_name}】未能格式化索引器 '{indexer_name}' 的MoviePilot配置。")

        if all_config_lines:
            logger.info(f"【{self.plugin_name}】为 {output_count} 个Jackett索引器生成的“自定义索引站点”配置 (请将以下所有行复制到自定义索引站点插件中，每行一个):")
            logger.info(f"MOVIEPILOT_CUSTOM_INDEXER_CONFIG_BLOCK_START")
            for line in all_config_lines:
                logger.info(line)
            logger.info(f"MOVIEPILOT_CUSTOM_INDEXER_CONFIG_BLOCK_END")
            logger.info(f"【{self.plugin_name}】共 {output_count} 条配置已记录。")
        else:
            logger.warn(f"【{self.plugin_name}】虽然获取了原始索引器，但未能成功生成任何配置字符串。")
        logger.info(f"【{self.plugin_name}】Jackett索引器配置记录过程结束。")

    def get_form(self) -> Tuple[List[dict], dict]:
        return [
            {'component': 'VAlert', 'props': {'type': 'info', 'text': '启用并配置Jackett服务器信息后，插件会自动获取Jackett中的索引器，并将其“自定义索引站点”配置字符串输出到MoviePilot的日志中。您需要从日志中复制这些配置。', 'class': 'mb-4'}},
            {'component': 'VSwitch', 'props': {'model': 'enabled', 'label': '启用插件'}},
            {'component': 'VTextField', 'props': {'model': 'host', 'label': 'Jackett地址', 'placeholder': 'http://localhost:9117', 'hint': '请输入Jackett的完整地址，包括http或https前缀。'}},
            {'component': 'VTextField', 'props': {'model': 'api_key', 'label': 'API Key', 'type': 'password', 'placeholder': 'Jackett管理界面右上角的API Key'}},
            {'component': 'VTextField', 'props': {'model': 'password', 'label': 'Jackett管理密码 (可选)', 'type': 'password', 'placeholder': 'Jackett管理界面配置的Admin password，如未配置可为空。API Key通常已足够。'}},
            {
                'component': 'VBtn',
                'props': {
                    'color': 'secondary',
                    'class': 'mt-4',
                    'block': True,
                },
                'text': '手动记录Jackett索引器配置到日志',
                'events': [
                    {
                        'name': 'click',
                        'value': "() => { this.$axios.get('/api/v1/plugin/Jackett/jackett/trigger_log_configs').then(res => this.$toast.info(res.data.message || '操作完成，请查看日志。')).catch(err => this.$toast.error('触发日志记录失败: ' + (err.response?.data?.message || err.message))); }"
                    }
                ]
            }
        ], {"enabled": False, "host": "", "api_key": "", "password": ""}

    def get_state(self) -> bool:
        return self._enabled

    def stop_service(self) -> None:
        logger.info(f"【{self.plugin_name} ({self.__class__.__name__})】插件服务已停止。")

    def get_page(self) -> Optional[List[dict]]:
        return None 

    def get_api(self) -> List[dict]:
        return [
            {
                "path": "/jackett/trigger_log_configs",
                "endpoint": self.api_trigger_log_configs,
                "methods": ["GET"],
                "summary": "手动触发记录Jackett索引器配置到日志",
                "description": "调用此API会使插件重新获取Jackett索引器并将其配置输出到日志。"
            }
        ]

    def api_trigger_log_configs(self):
        logger.info(f"【{self.plugin_name}】收到手动触发记录Jackett配置的API请求。")
        if not self._enabled:
            logger.warn(f"【{self.plugin_name}】插件未启用，无法手动记录配置。")
            return {"code": 1, "message": "插件未启用，请先在设置中启用。"}
        if not self._host or not self._api_key:
            logger.warn(f"【{self.plugin_name}】Jackett Host或API Key未配置，无法手动记录配置。")
            return {"code": 1, "message": "Jackett Host或API Key未配置，请在插件设置中配置。"}
        
        self.log_jackett_indexer_configs()
        return {"code": 0, "message": "已尝试记录Jackett索引器配置到MoviePilot日志，请查看日志获取结果。"}