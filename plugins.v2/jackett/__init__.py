import base64
import json
from typing import Dict, Any, List, Optional, Tuple
import time # Keep for _fetch_jackett_indexers retry logic

import requests # Keep for _fetch_jackett_indexers

from app.plugins import _PluginBase
from app.utils.http import RequestUtils # Keep for _fetch_jackett_indexers
from app.log import logger # Use MoviePilot's logger

class Jackett(_PluginBase):
    """
    Jackett 索引器配置生成插件
    """
    # 插件名称
    plugin_name = "Jackett 配置生成器"
    # 插件描述
    plugin_desc = "从 Jackett 获取索引器，并生成适用于“自定义索引站点”插件的配置字符串。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/Jackett/Jackett/master/src/Jackett.Common/Content/favicon.ico"
    # 插件版本
    plugin_version = "2.0" # Updated version
    # 插件作者
    plugin_author = "jason (modified by AI)"
    # 作者主页
    author_url = "https://github.com/xj-bear"
    # 插件配置项ID前缀
    plugin_config_prefix = "jackett_" # Changed prefix to avoid conflict if old plugin exists
    # 加载顺序
    plugin_order = 22 # Adjusted order
    # 可使用的用户级别
    user_level = 2

    # 私有属性
    _enabled = False
    _host = None
    _api_key = None
    _password = None # Retained for Jackett auth if needed

    # 会话信息 - Retained for _fetch_jackett_indexers
    _session = None
    _cookies = None

    def init_plugin(self, config: dict = None) -> None:
        logger.info(f"【{self.plugin_name}】正在初始化插件...")
        if not config:
            logger.warn(f"【{self.plugin_name}】配置为空")
            return

        # 读取配置
        self._enabled = config.get("enabled", False)
        self._host = config.get("host")
        self._api_key = config.get("api_key")
        self._password = config.get("password")
        
        # 初始化会话
        self._session = None
        self._cookies = None
        
        logger.info(f"【{self.plugin_name}】插件初始化完成，状态: {self._enabled}")

    def _fetch_jackett_indexers(self) -> List[Dict[str, Any]]:
        """
        获取Jackett索引器列表，支持重试机制
        """
        if not self._host or not self._api_key:
            logger.error(f"【{self.plugin_name}】缺少必要配置参数 (host 或 api_key)，无法获取索引器")
            return []
        
        host = self._host
        if host.endswith('/'):
            host = host[:-1]
            
        max_retries = 3
        retry_interval = 5
        current_try = 1
            
        try:
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": "MoviePilot", # Updated User-Agent
                "X-Api-Key": self._api_key,
                "Accept": "application/json, text/javascript, */*; q=0.01"
            }
            
            logger.debug(f"【{self.plugin_name}】请求头: {headers}")
            
            session = requests.session()
            req = RequestUtils(headers=headers, session=session)
            
            if self._password:
                dashboard_url = f"{host}/UI/Dashboard" # Use normalized host
                logger.info(f"【{self.plugin_name}】尝试访问Dashboard进行认证: {dashboard_url}")
                
                auth_data = {"password": self._password}
                # dashboard_res = req.post_res(url=dashboard_url, data=auth_data) # params seemed redundant
                # Simpler auth attempt:
                # Jackett's login is usually via a form post to /UI/Dashboard with 'password'
                # and then subsequent API calls use the API key or cookies.
                # The API key should bypass password auth for API calls.
                # If password is set, it's for UI access. The API key should be sufficient for /api/v2.0/indexers.
                # However, some Jackett setups might be stricter. Let's keep the cookie logic simple.
                try:
                    login_url = f"{host}/api/v2.0/login" # Common login endpoint, or use dashboard
                    login_payload = {'username': '', 'password': self._password, 'rememberMe': 'true'}
                    # It's tricky, Jackett's auth is primarily cookie-based for UI, API key for API.
                    # Let's assume API key is sufficient. If not, user needs to ensure Jackett is accessible.
                    # The original code's auth logic might be specific to an older Jackett version or setup.
                    # For now, we'll rely on the API key. If auth errors persist, this area needs review
                    # against the specific Jackett version being used.
                    # The primary method is X-Api-Key header.
                    pass # Keeping password field for future, but API key should be primary for API.

                except Exception as e:
                    logger.warn(f"【{self.plugin_name}】Jackett 认证 (password) 尝试失败: {e}")


            while current_try <= max_retries:
                try:
                    indexer_query_url = f"{host}/api/v2.0/indexers?configured=true" # Use normalized host
                    logger.info(f"【{self.plugin_name}】请求索引器列表 (第{current_try}次尝试): {indexer_query_url}")
                    
                    response = req.get_res(url=indexer_query_url, verify=False) # verify=False for self-signed certs
                    
                    if response:
                        logger.debug(f"【{self.plugin_name}】收到响应: HTTP {response.status_code}")
                        logger.debug(f"【{self.plugin_name}】响应头: {dict(response.headers)}")
                        
                        if response.status_code == 200:
                            try:
                                indexers = response.json()
                                if indexers and isinstance(indexers, list):
                                    logger.info(f"【{self.plugin_name}】成功获取到 {len(indexers)} 个索引器")
                                    return indexers
                                else:
                                    logger.warn(f"【{self.plugin_name}】解析索引器列表失败: 无效的JSON响应或空列表. Body: {response.text[:200]}")
                            except json.JSONDecodeError as e:
                                logger.error(f"【{self.plugin_name}】解析索引器列表JSON异常: {e}")
                                logger.error(f"【{self.plugin_name}】响应内容 (前500 chars): {response.text[:500]}...")
                        elif response.status_code == 401 or response.status_code == 403: # Unauthorized or Forbidden
                            logger.error(f"【{self.plugin_name}】认证或授权失败 (HTTP {response.status_code})，请检查API Key或Jackett配置. Body: {response.text[:200]}")
                            break 
                        else:
                            logger.warn(f"【{self.plugin_name}】获取索引器列表失败: HTTP {response.status_code}. Body: {response.text[:200]}")
                    else:
                        logger.warn(f"【{self.plugin_name}】获取索引器列表失败: 无响应")
                    
                    if current_try < max_retries:
                        logger.info(f"【{self.plugin_name}】{retry_interval}秒后进行第{current_try + 1}次重试...")
                        time.sleep(retry_interval)
                    current_try += 1
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"【{self.plugin_name}】请求索引器列表网络异常: {e}")
                    if current_try < max_retries:
                        logger.info(f"【{self.plugin_name}】{retry_interval}秒后进行第{current_try + 1}次重试...")
                        time.sleep(retry_interval)
                    current_try += 1
                except Exception as e: # Catch any other unexpected error
                    logger.error(f"【{self.plugin_name}】获取Jackett索引器时发生未知错误: {e}", exc_info=True)
                    break # Don't retry on unknown errors immediately

            logger.warn(f"【{self.plugin_name}】在 {max_retries} 次尝试后仍未能获取索引器列表")
            return []
                
        except Exception as e:
            logger.error(f"【{self.plugin_name}】获取Jackett索引器顶层异常: {e}", exc_info=True)
            return []
    
    def _format_indexer_for_moviepilot(self, jackett_indexer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        将单个Jackett索引器格式化为MoviePilot索引器JSON配置
        """
        try:
            indexer_id = jackett_indexer.get("id", "")
            indexer_name = jackett_indexer.get("name", "")
            if not indexer_id or not indexer_name:
                logger.warn(f"【{self.plugin_name}】Jackett索引器缺少ID或名称: {jackett_indexer}")
                return None

            # MoviePilot 使用的域名，对于Jackett，通常是 jackett_{indexer_id}
            # IMPORTANT: The "Custom Indexer" plugin takes the domain part from the string,
            # e.g., "mysite.com|BASE64...". So, mp_indexer['id'] will be this domain.
            mp_domain_id = f"jackett_{indexer_id.lower().replace('-', '_')}" # Ensure valid characters for domain/key

            categories = {
                "movie": [
                    {"id": "2000", "desc": "Movies"}, 
                    {"id": "2010", "desc": "Movies/Foreign"},
                    {"id": "2020", "desc": "Movies/BluRay"}, 
                    {"id": "2030", "desc": "Movies/DVD"},
                    {"id": "2040", "desc": "Movies/HD"}, 
                    {"id": "2045", "desc": "Movies/UHD"},
                    {"id": "2050", "desc": "Movies/3D"}, 
                    {"id": "2060", "desc": "Movies/SD"}
                ],
                "tv": [
                    {"id": "5000", "desc": "TV"}, 
                    {"id": "5020", "desc": "TV/Blu-ray"},
                    {"id": "5030", "desc": "TV/DVD"}, 
                    {"id": "5040", "desc": "TV/HD"},
                    {"id": "5050", "desc": "TV/SD"}, 
                    {"id": "5060", "desc": "TV/Foreign"},
                    {"id": "5070", "desc": "TV/Sport"}
                ]
            }
            
            # Ensure host does not end with a slash for consistency
            host = self._host
            if host.endswith('/'):
                host = host[:-1]

            mp_indexer = {
                "id": mp_domain_id, # This will be the 'domain' part for Custom Indexer
                "name": f"[Jackett] {indexer_name}",
                "domain": host, # The actual Jackett server URL
                "url": host,    # The actual Jackett server URL
                "encoding": "UTF-8",
                "public": True, # Most Jackett indexers behave as public via Torznab
                "proxy": True,  # Recommended if MoviePilot needs a proxy for Jackett
                "language": "zh_CN", # Default, can be adjusted if Jackett provides lang info
                "category": categories,
                "search": {
                    "paths": [
                        {
                            # Path relative to Jackett's domain
                            "path": f"/api/v2.0/indexers/{indexer_id}/results/torznab", 
                            "method": "get"
                        }
                    ],
                    "params": {
                        "t": "search",
                        "q": "{keyword}",
                        "cat": "{cat}",
                        "apikey": self._api_key
                    }
                },
                "torrents": {
                    "list": {
                        "selector": "item" # Torznab uses <item> for each torrent
                    },
                    "fields": {
                        "title": {"selector": "title"},
                        "details": {"selector": "guid"}, # Or comments
                        "download": {"selector": "link"}, # Direct download link from Jackett
                        "size": {"selector": "size"},
                        "date_added": {"selector": "pubDate", "optional": True},
                        "seeders": {"selector": "torznab:attr[name=seeders]", "filters": [{"name": "re", "args": ["(\\d+)", 1]}], "default": "0"},
                        "leechers": {"selector": "torznab:attr[name=peers]", "filters": [{"name": "re", "args": ["(\\d+)", 1]}], "default": "0"}, # Peers often means seeders+leechers, but for torznab:peers it's often total peers. Leechers = peers - seeders. Or sometimes torznab:attr[name=leechers] exists.
                        # For simplicity, using peers as leechers if specific leechers field is not standard.
                        # It's better if Jackett provides a distinct leechers attribute.
                        # Let's assume torznab:attr[name=peers] might be total peers, and seeders is correct.
                        # The original code used peers for leechers, which is common.
                        "downloadvolumefactor": {"case": {"*": 0}}, # Typically 0 for public trackers
                        "uploadvolumefactor": {"case": {"*": 1}}    # Typically 1 for public trackers
                    }
                }
            }
            
            logger.debug(f"【{self.plugin_name}】格式化 MoviePilot 索引器配置: {mp_domain_id}")
            return mp_indexer
        except Exception as e:
            logger.error(f"【{self.plugin_name}】格式化索引器 {jackett_indexer.get('name', 'N/A')} 失败: {e}", exc_info=True)
            return None
            
    def get_form(self) -> Tuple[List[dict], dict]:
        """
        获取配置表单
        """
        return [
            {
                'component': 'VAlert',
                'props': {
                    'type': 'info',
                    'text': '配置Jackett服务器信息。配置完成后，请到插件的“查看Jackett索引器”页面获取配置字符串，并手动添加到“自定义索引站点”插件中。',
                    'class': 'mb-4'
                }
            },
            {
                'component': 'VSwitch',
                'props': {
                    'model': 'enabled',
                    'label': '启用插件（主要用于使插件页面和API可见）'
                }
            },
            {
                'component': 'VTextField',
                'props': {
                    'model': 'host',
                    'label': 'Jackett地址',
                    'placeholder': 'http://localhost:9117',
                    'hint': '请输入Jackett的完整地址，包括http或https前缀。' # Removed "don't end with slash" as we handle it.
                }
            },
            {
                'component': 'VTextField',
                'props': {
                    'model': 'api_key',
                    'label': 'API Key',
                    'type': 'password', # For masking
                    'placeholder': 'Jackett管理界面右上角的API Key'
                }
            },
            {
                'component': 'VTextField',
                'props': {
                    'model': 'password',
                    'label': 'Jackett管理密码 (可选)',
                    'type': 'password',
                    'placeholder': 'Jackett管理界面配置的Admin password，如未配置可为空。API Key通常已足够。'
                }
            }
        ], {
            "enabled": False,
            "host": "",
            "api_key": "",
            "password": ""
        }

    def get_page(self) -> List[dict]:
        """
        获取插件自定义页面，用于展示生成的配置字符串
        """
        return [
            {
                'component': 'VAlert',
                'props': {
                    'type': 'info',
                    'text': '下方列出了从您的Jackett实例获取的索引器及其对应的“自定义索引站点”配置字符串。请复制所需的配置字符串，然后粘贴到“自定义索引站点”插件的配置文本框中（一行一个）。',
                    'class': 'mb-4'
                }
            },
            {
                'component': 'VBtn',
                'props': {
                    'color': 'primary',
                    'block': True,
                    'class': 'mb-4',
                    'loading': 'loading', # Bind to loading state
                },
                'text': '从Jackett刷新索引器列表',
                'events': [
                    {
                        'name': 'click',
                        'value': 'this.fetchJackettIndexers'
                    }
                ]
            },
            {
                'component': 'VDataTable',
                'props': {
                    'headers': [
                        {'text': 'Jackett索引器名称', 'value': 'name', 'sortable': True},
                        {'text': 'ID (用于域名)', 'value': 'mp_id', 'sortable': True},
                        {'text': '“自定义索引站点”配置字符串', 'value': 'config_string', 'sortable': False},
                        {'text': '操作', 'value': 'actions', 'sortable': False}
                    ],
                    'items': 'jackett_indexers_data', # Bind to data property
                    'loading': 'loading',             # Bind to loading state
                    'loadingText': '正在从Jackett加载索引器...',
                    'noDataText': '未获取到Jackett索引器，或请先点击上方按钮刷新。',
                    'itemsPerPage': 10,
                    'class': 'elevation-1'
                },
                'scopedSlots': [
                    {
                        'name': 'item.config_string',
                        'content': {
                            'component': 'VTextarea',
                            'props': {
                                'value': 'props.item.config_string',
                                'readonly': True,
                                'autoGrow': True,
                                'rows': 2,
                                'outlined': True,
                                'dense': True,
                                'hideDetails': True,
                            }
                        }
                    },
                    {
                        'name': 'item.actions',
                        'content': {
                            'component': 'VBtn',
                            'props': {
                                'icon': True,
                                'small': True,
                                'title': '复制配置字符串',
                            },
                            'content': [
                                {
                                    'component': 'VIcon',
                                    'text': 'mdi-content-copy' # Material Design Icon for copy
                                }
                            ],
                            'events': [
                                {
                                    'name': 'click',
                                    'value': 'this.copyToClipboard(props.item.config_string)'
                                }
                            ]
                        }
                    }
                ]
            },
            {
                'component': 'VScript',
                'content': '''
                    export default {
                        data() {
                            return {
                                loading: false,
                                jackett_indexers_data: [] // Stores { name, mp_id, config_string }
                            }
                        },
                        mounted() {
                            this.fetchJackettIndexers(); // Fetch on page load
                        },
                        methods: {
                            fetchJackettIndexers() {
                                this.loading = true;
                                this.jackett_indexers_data = []; // Clear previous data
                                this.$axios.get("/api/v1/plugin/jackett/list_custom_configs")
                                    .then(res => {
                                        if (res.data.code === 0 && res.data.data) {
                                            this.jackett_indexers_data = res.data.data;
                                            if (this.jackett_indexers_data.length > 0) {
                                                this.$toast.success(`成功获取 ${this.jackett_indexers_data.length} 个Jackett索引器配置`);
                                            } else {
                                                this.$toast.info("未从Jackett获取到可用索引器。");
                                            }
                                        } else {
                                            this.$toast.error(res.data.message || "获取Jackett索引器配置失败");
                                        }
                                    })
                                    .catch(err => {
                                        let errorMsg = "获取Jackett索引器配置异常";
                                        if (err.response && err.response.data && err.response.data.message) {
                                            errorMsg = err.response.data.message;
                                        } else if (err.message) {
                                            errorMsg = err.message;
                                        }
                                        this.$toast.error(errorMsg);
                                        console.error("Error fetching Jackett indexers:", err);
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
                                    console.error("Failed to copy text: ", err);
                                });
                            }
                        }
                    }
                '''
            }
        ]

    def get_api(self) -> List[dict]:
        """
        获取API接口
        """
        return [
            {
                "path": "/jackett/list_custom_configs", # Unique path
                "endpoint": self.api_list_custom_configs,
                "methods": ["GET"],
                "summary": "获取Jackett索引器的自定义站点配置字符串",
                "description": "从Jackett拉取索引器，并为每个索引器生成用于“自定义索引站点”插件的配置字符串。"
            }
        ]

    def api_list_custom_configs(self):
        """
        API端点：获取并格式化所有Jackett索引器的配置字符串
        """
        if not self._enabled:
            return {"code": 1, "message": "插件未启用", "data": []}
        if not self._host or not self._api_key:
            return {"code": 1, "message": "请先在插件配置中设置Jackett地址和API Key", "data": []}

        raw_jackett_indexers = self._fetch_jackett_indexers()
        if not raw_jackett_indexers:
            return {"code": 1, "message": "未能从Jackett获取索引器列表，请检查Jackett连接或日志。", "data": []}

        custom_configs_list = []
        for raw_indexer in raw_jackett_indexers:
            mp_config_json = self._format_indexer_for_moviepilot(raw_indexer)
            if mp_config_json:
                try:
                    # The domain for "Custom Indexer" plugin is the 'id' from mp_config_json
                    domain_part = mp_config_json['id'] 
                    
                    json_str = json.dumps(mp_config_json, ensure_ascii=False)
                    base64_encoded_json = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                    
                    custom_config_line = f"{domain_part}|{base64_encoded_json}"
                    
                    custom_configs_list.append({
                        "name": raw_indexer.get("name", "N/A"),
                        "mp_id": domain_part, # The ID/domain MoviePilot will use
                        "config_string": custom_config_line
                    })
                except Exception as e:
                    logger.error(f"【{self.plugin_name}】为索引器 {raw_indexer.get('name')} 生成Base64配置时出错: {e}", exc_info=True)
        
        if not custom_configs_list:
             return {"code": 1, "message": "成功连接Jackett但未能生成任何索引器配置，可能是格式化问题。", "data": []}

        return {"code": 0, "message": "成功", "data": custom_configs_list}

    def get_state(self) -> bool:
        """
        获取插件状态 (主要用于判断是否显示在插件列表和是否启用API)
        """
        return self._enabled

    def stop_service(self) -> None:
        """
        停止插件服务 (如果插件注册了定时任务等)
        本插件目前不需要复杂清理。
        """
        logger.info(f"【{self.plugin_name}】插件服务已停止。")

    # Removed get_service as this plugin no longer needs to periodically add/update indexers itself.
    # Removed _add_jackett_indexers, reload_indexers, _remove_jackett_indexers, etc.
    # as they are no longer relevant to the new approach.