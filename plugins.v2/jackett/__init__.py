import base64
import json
from typing import Dict, Any, List, Optional, Tuple
import time

import requests

from app.plugins import _PluginBase
from app.utils.http import RequestUtils
from app.log import logger

class Jackett(_PluginBase): # 类名保持为 Jackett
    """
    Jackett 索引器配置生成插件
    """
    # 插件名称 (UI显示名称，可以不变)
    plugin_name = "Jackett 配置生成器"
    # 插件描述
    plugin_desc = "从 Jackett 获取索引器，并生成适用于“自定义索引站点”插件的配置字符串。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/Jackett/Jackett/master/src/Jackett.Common/Content/favicon.ico"
    # 插件版本
    plugin_version = "2.1" # Incremented version
    # 插件作者
    plugin_author = "jason (modified by AI)"
    # 作者主页
    author_url = "https://github.com/xj-bear"
    # 插件配置项ID前缀 (保持 "jackett_")
    plugin_config_prefix = "jackett_"
    # 加载顺序
    plugin_order = 22
    # 可使用的用户级别
    user_level = 2

    _enabled = False
    _host = None
    _api_key = None
    _password = None
    _session = None
    _cookies = None

    def init_plugin(self, config: dict = None) -> None:
        logger.info(f"【{self.plugin_name} ({self.__class__.__name__})】正在初始化插件...")
        if not config:
            logger.warn(f"【{self.plugin_name} ({self.__class__.__name__})】配置为空")
            return

        self._enabled = config.get("enabled", False)
        self._host = config.get("host")
        self._api_key = config.get("api_key")
        self._password = config.get("password")
        
        self._session = None
        self._cookies = None
        
        logger.info(f"【{self.plugin_name} ({self.__class__.__name__})】初始化完成。Enabled: {self._enabled}, Host: {'SET' if self._host else 'NOT SET'}, API Key: {'SET' if self._api_key else 'NOT SET'}")

    def _fetch_jackett_indexers(self) -> List[Dict[str, Any]]:
        logger.info(f"【{self.plugin_name}】'_fetch_jackett_indexers' CALLED. Host: {self._host}, API Key: {'[SET]' if self._api_key else '[NOT SET]'}")
        if not self._host or not self._api_key:
            logger.error(f"【{self.plugin_name}】Jackett Host 或 API Key 未配置，无法获取索引器。")
            return []
        
        host = self._host.rstrip('/') # Ensure no trailing slash
            
        max_retries = 3
        retry_interval = 5
        current_try = 1
            
        # Prepare session and headers outside the loop
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": f"MoviePilot-Plugin-{self.__class__.__name__}/{self.plugin_version}", # Dynamic User-Agent
            "X-Api-Key": self._api_key,
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }
        session = requests.session() # Create a session object

        while current_try <= max_retries:
            try:
                indexer_query_url = f"{host}/api/v2.0/indexers?configured=true"
                logger.info(f"【{self.plugin_name}】请求Jackett索引器列表 (尝试 {current_try}/{max_retries}): {indexer_query_url}")
                
                # Use the session to make the request
                response = session.get(indexer_query_url, headers=headers, verify=False, timeout=20)
                
                logger.debug(f"【{self.plugin_name}】Jackett响应状态: {response.status_code}")
                if response.headers:
                     logger.debug(f"【{self.plugin_name}】Jackett响应头: {dict(response.headers)}")

                if response.status_code == 200:
                    try:
                        indexers = response.json()
                        if indexers and isinstance(indexers, list):
                            logger.info(f"【{self.plugin_name}】成功从Jackett获取到 {len(indexers)} 个索引器。")
                            return indexers
                        else:
                            logger.warn(f"【{self.plugin_name}】从Jackett获取的索引器列表为空或格式无效. 响应体 (前200字符): {response.text[:200]}")
                            return [] # Return empty list if valid json but empty or wrong type
                    except json.JSONDecodeError as e:
                        logger.error(f"【{self.plugin_name}】解析Jackett响应JSON失败: {e}")
                        logger.error(f"【{self.plugin_name}】Jackett响应内容 (前500字符): {response.text[:500]}...")
                        return [] # Critical error, stop retrying for this type
                elif response.status_code in [401, 403]:
                    logger.error(f"【{self.plugin_name}】Jackett认证或授权失败 (HTTP {response.status_code})。请检查API Key。响应体 (前200字符): {response.text[:200]}")
                    return [] # Critical auth error, stop retrying
                else:
                    logger.warn(f"【{self.plugin_name}】从Jackett获取索引器列表失败: HTTP {response.status_code}. 响应体 (前200字符): {response.text[:200]}")
                
            except requests.exceptions.Timeout:
                logger.warn(f"【{self.plugin_name}】请求Jackett超时 (尝试 {current_try}/{max_retries}).")
            except requests.exceptions.RequestException as e:
                logger.error(f"【{self.plugin_name}】请求Jackett网络异常 (尝试 {current_try}/{max_retries}): {e}")
            except Exception as e: 
                logger.error(f"【{self.plugin_name}】获取Jackett索引器时发生未知错误 (尝试 {current_try}/{max_retries}): {e}", exc_info=True)
                # For unknown errors, maybe retry once more, but could be persistent
            
            if current_try < max_retries:
                logger.info(f"【{self.plugin_name}】将在 {retry_interval} 秒后重试...")
                time.sleep(retry_interval)
            current_try += 1

        logger.warn(f"【{self.plugin_name}】经过 {max_retries} 次尝试后，未能成功获取Jackett索引器列表。")
        return []
    
    def _format_indexer_for_moviepilot(self, jackett_indexer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            indexer_id = jackett_indexer.get("id", "")
            indexer_name = jackett_indexer.get("name", "")
            if not indexer_id or not indexer_name:
                logger.warn(f"【{self.plugin_name}】Jackett索引器数据不完整 (缺少ID或名称): {jackett_indexer}")
                return None

            mp_domain_id = f"jackett_{indexer_id.lower().replace('-', '_')}" 

            categories = {
                "movie": [{"id": "2000", "desc": "Movies"}, {"id": "2010", "desc": "Movies/Foreign"}, {"id": "2020", "desc": "Movies/BluRay"}, {"id": "2030", "desc": "Movies/DVD"}, {"id": "2040", "desc": "Movies/HD"}, {"id": "2045", "desc": "Movies/UHD"}, {"id": "2050", "desc": "Movies/3D"}, {"id": "2060", "desc": "Movies/SD"}],
                "tv": [{"id": "5000", "desc": "TV"}, {"id": "5020", "desc": "TV/Blu-ray"}, {"id": "5030", "desc": "TV/DVD"}, {"id": "5040", "desc": "TV/HD"}, {"id": "5050", "desc": "TV/SD"}, {"id": "5060", "desc": "TV/Foreign"}, {"id": "5070", "desc": "TV/Sport"}]
            }
            
            host = self._host.rstrip('/')

            mp_indexer = {
                "id": mp_domain_id, 
                "name": f"[Jackett] {indexer_name}",
                "domain": host, 
                "url": host,    
                "encoding": "UTF-8",
                "public": True, 
                "proxy": True,  
                "language": "zh_CN", 
                "category": categories,
                "search": {
                    "paths": [{"path": f"/api/v2.0/indexers/{indexer_id}/results/torznab", "method": "get"}],
                    "params": {"t": "search", "q": "{keyword}", "cat": "{cat}", "apikey": self._api_key}
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
            logger.debug(f"【{self.plugin_name}】格式化MoviePilot索引器配置完成: {mp_domain_id}")
            return mp_indexer
        except Exception as e:
            logger.error(f"【{self.plugin_name}】格式化索引器 '{jackett_indexer.get('name', 'N/A')}' 失败: {e}", exc_info=True)
            return None
            
    def get_form(self) -> Tuple[List[dict], dict]:
        return [
            {'component': 'VAlert', 'props': {'type': 'info', 'text': '配置Jackett服务器信息。配置完成后，请到插件的“查看Jackett索引器”页面获取配置字符串，并手动添加到“自定义索引站点”插件中。', 'class': 'mb-4'}},
            {'component': 'VSwitch', 'props': {'model': 'enabled', 'label': '启用插件（主要用于使插件页面和API可见）'}},
            {'component': 'VTextField', 'props': {'model': 'host', 'label': 'Jackett地址', 'placeholder': 'http://localhost:9117', 'hint': '请输入Jackett的完整地址，包括http或https前缀。'}},
            {'component': 'VTextField', 'props': {'model': 'api_key', 'label': 'API Key', 'type': 'password', 'placeholder': 'Jackett管理界面右上角的API Key'}},
            {'component': 'VTextField', 'props': {'model': 'password', 'label': 'Jackett管理密码 (可选)', 'type': 'password', 'placeholder': 'Jackett管理界面配置的Admin password，如未配置可为空。API Key通常已足够。'}}
        ], {"enabled": False, "host": "", "api_key": "", "password": ""}

    def get_page(self) -> List[dict]:
        return [
            {'component': 'VAlert', 'props': {'type': 'info', 'text': '下方列出了从您的Jackett实例获取的索引器及其对应的“自定义索引站点”配置字符串。请复制所需的配置字符串，然后粘贴到“自定义索引站点”插件的配置文本框中（一行一个）。', 'class': 'mb-4'}},
            {'component': 'VBtn', 'props': {'color': 'primary', 'block': True, 'class': 'mb-4', 'loading': 'loading'}, 'text': '从Jackett刷新索引器列表', 'events': [{'name': 'click', 'value': 'this.fetchJackettIndexers'}]},
            {'component': 'VDataTable', 'props': {'headers': [{'text': 'Jackett索引器名称', 'value': 'name', 'sortable': True}, {'text': 'ID (用于域名)', 'value': 'mp_id', 'sortable': True}, {'text': '“自定义索引站点”配置字符串', 'value': 'config_string', 'sortable': False}, {'text': '操作', 'value': 'actions', 'sortable': False}], 'items': 'jackett_indexers_data', 'loading': 'loading', 'loadingText': '正在从Jackett加载索引器...', 'noDataText': '未获取到Jackett索引器，或请先点击上方按钮刷新。', 'itemsPerPage': 10, 'class': 'elevation-1'},
             'scopedSlots': [
                 {'name': 'item.config_string', 'content': {'component': 'VTextarea', 'props': {'value': 'props.item.config_string', 'readonly': True, 'autoGrow': True, 'rows': 2, 'outlined': True, 'dense': True, 'hideDetails': True, 'class': 'pt-2 pb-2'}}},
                 {'name': 'item.actions', 'content': {'component': 'VBtn', 'props': {'icon': True, 'small': True, 'title': '复制配置字符串'}, 'content': [{'component': 'VIcon', 'text': 'mdi-content-copy'}], 'events': [{'name': 'click', 'value': 'this.copyToClipboard(props.item.config_string)'}]}}
             ]},
            {'component': 'VScript', 'content': '''
                    export default {
                        data() {
                            return {
                                loading: false,
                                jackett_indexers_data: [] 
                            }
                        },
                        mounted() {
                            // Optional: Automatically fetch on page load, or rely on button.
                            // this.fetchJackettIndexers(); 
                        },
                        methods: {
                            fetchJackettIndexers() {
                                this.loading = true;
                                this.jackett_indexers_data = []; 
                                // CRITICAL: Ensure this path matches the registered API path from logs
                                // Based on logs: /api/v1/plugin/Jackett/jackett/list_custom_configs
                                const apiUrl = "/api/v1/plugin/Jackett/jackett/list_custom_configs"; 
                                console.log("[Jackett Plugin Page] Requesting API: " + apiUrl);
                                this.$axios.get(apiUrl)
                                    .then(res => {
                                        console.log("[Jackett Plugin Page] API Response:", res);
                                        if (res.data && res.data.code === 0 && res.data.data) {
                                            this.jackett_indexers_data = res.data.data;
                                            if (this.jackett_indexers_data.length > 0) {
                                                this.$toast.success(`成功获取 ${this.jackett_indexers_data.length} 个Jackett索引器配置`);
                                            } else {
                                                this.$toast.info("未从Jackett获取到可用索引器，或它们未能正确格式化。检查MoviePilot日志获取更多信息。");
                                            }
                                        } else {
                                            const errorMsg = res.data ? (res.data.message || "获取Jackett索引器配置失败，响应代码非0或无数据。") : "获取Jackett索引器配置失败，响应无效。";
                                            this.$toast.error(errorMsg);
                                            console.error("[Jackett Plugin Page] Error fetching/processing data:", errorMsg, res.data);
                                        }
                                    })
                                    .catch(err => {
                                        console.error("[Jackett Plugin Page] API request error:", err);
                                        let errorMsg = "请求Jackett索引器配置时发生网络或未知错误。";
                                        if (err.response && err.response.data && err.response.data.message) {
                                            errorMsg = err.response.data.message;
                                        } else if (err.message) {
                                            errorMsg = err.message;
                                        }
                                        this.$toast.error(errorMsg);
                                    })
                                    .finally(() => {
                                        this.loading = false;
                                    });
                            },
                            copyToClipboard(text) {
                                navigator.clipboard.writeText(text).then(() => {
                                    this.$toast.success("配置已复制到剪贴板！");
                                }).catch(err => {
                                    this.$toast.error("复制失败: " + err);
                                    console.error("[Jackett Plugin Page] Failed to copy text: ", err);
                                });
                            }
                        }
                    }
                '''
            }
        ]

    def get_api(self) -> List[dict]:
        logger.debug(f"【{self.plugin_name} ({self.__class__.__name__})】'get_api' CALLED.")
        return [
            {
                # This path's first segment "jackett" (lowercase) will be appended
                # to the base plugin route "/api/v1/plugin/Jackett/" (uppercase "Jackett" from class/folder name)
                "path": "/jackett/list_custom_configs", 
                "endpoint": self.api_list_custom_configs,
                "methods": ["GET"],
                "summary": "获取Jackett索引器的自定义站点配置字符串",
                "description": "从Jackett拉取索引器，并为每个索引器生成用于“自定义索引站点”插件的配置字符串。"
            }
        ]

    def api_list_custom_configs(self):
        logger.info(f"【{self.plugin_name}】API '/jackett/list_custom_configs' CALLED.")
        if not self._enabled:
            logger.warn(f"【{self.plugin_name}】API调用失败：插件未启用。")
            return {"code": 1, "message": "插件未启用", "data": []}
        if not self._host or not self._api_key:
            logger.warn(f"【{self.plugin_name}】API调用失败：Jackett Host 或 API Key 未配置。")
            return {"code": 1, "message": "请先在插件配置中设置Jackett地址和API Key", "data": []}

        raw_jackett_indexers = self._fetch_jackett_indexers()
        if not raw_jackett_indexers: # _fetch_jackett_indexers already logs errors
            return {"code": 1, "message": "未能从Jackett获取索引器列表，请检查MoviePilot日志以获取详细错误信息。", "data": []}

        custom_configs_list = []
        for raw_indexer in raw_jackett_indexers:
            mp_config_json = self._format_indexer_for_moviepilot(raw_indexer)
            if mp_config_json:
                try:
                    domain_part = mp_config_json['id'] 
                    json_str = json.dumps(mp_config_json, ensure_ascii=False)
                    base64_encoded_json = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                    custom_config_line = f"{domain_part}|{base64_encoded_json}"
                    
                    custom_configs_list.append({
                        "name": raw_indexer.get("name", "N/A"),
                        "mp_id": domain_part,
                        "config_string": custom_config_line
                    })
                except Exception as e:
                    logger.error(f"【{self.plugin_name}】为索引器 '{raw_indexer.get('name')}' 生成Base64配置时出错: {e}", exc_info=True)
        
        if not custom_configs_list and raw_jackett_indexers: # Fetched some, but formatted none
             logger.warn(f"【{self.plugin_name}】成功连接Jackett并获取 {len(raw_jackett_indexers)} 个索引器，但未能为任何一个生成配置（可能是格式化问题）。")
             return {"code": 1, "message": "成功连接Jackett，但未能生成任何有效的索引器配置，请检查日志。", "data": []}
        elif not custom_configs_list: # Fetched none (already handled by first check on raw_jackett_indexers)
            pass # Already covered

        logger.info(f"【{self.plugin_name}】API调用成功，生成了 {len(custom_configs_list)} 条配置。")
        return {"code": 0, "message": "成功", "data": custom_configs_list}

    def get_state(self) -> bool:
        return self._enabled

    def stop_service(self) -> None:
        logger.info(f"【{self.plugin_name} ({self.__class__.__name__})】插件服务已停止。")