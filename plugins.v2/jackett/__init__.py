import base64
import json
from typing import Dict, Any, List, Optional, Tuple # Tuple might not be needed anymore
import time
import requests

from app.plugins import _PluginBase
# from app.utils.http import RequestUtils # We can use requests.session() directly
from app.log import logger

class Jackett(_PluginBase): # 类名保持为 Jackett
    """
    Jackett 索引器配置生成并输出到日志的插件
    """
    plugin_name = "Jackett 配置日志输出器" # 修改UI显示名称以反映新功能
    plugin_desc = "从 Jackett 获取索引器，格式化为“自定义索引站点”插件配置，并输出到 MoviePilot 日志中。"
    plugin_icon = "https://raw.githubusercontent.com/Jackett/Jackett/master/src/Jackett.Common/Content/favicon.ico"
    plugin_version = "3.0" # New version for this approach
    plugin_author = "jason (modified by AI)"
    author_url = "https://github.com/xj-bear"
    plugin_config_prefix = "jackett_" # 保持 "jackett_"
    plugin_order = 22
    user_level = 2 # Or appropriate level

    _enabled = False
    _host = None
    _api_key = None
    _password = None # Kept for completeness if Jackett needs it, though API key is primary

    # No _session or _cookies needed at class level if session is managed per-request

    def init_plugin(self, config: dict = None) -> None:
        logger.info(f"【{self.plugin_name} ({self.__class__.__name__})】正在初始化插件...")
        if not config:
            logger.warn(f"【{self.plugin_name} ({self.__class__.__name__})】配置为空，插件功能可能受限。")
            # Even if config is empty, we might want to allow enabling later.
            # So, don't return immediately unless absolutely necessary.
            # self._enabled will remain False if config is None or 'enabled' is not in config.

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
        # PASTE THE WORKING _fetch_jackett_indexers from the previous step here
        # This is the version that includes the pre-request/session logic
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
                dashboard_check_url = f"{host}/UI/Dashboard"
                try:
                    logger.info(f"【{self.plugin_name}】尝试GET登录页面: {login_url}")
                    session.get(login_url, verify=False, timeout=10) 
                    logger.info(f"【{self.plugin_name}】GET登录页面完成。当前Cookies: {session.cookies.get_dict()}")
                except requests.exceptions.RequestException as e:
                    logger.warn(f"【{self.plugin_name}】GET登录页面失败: {e}")
                login_submission_url = f"{host}/UI/Dashboard"
                login_post_headers = {
                    "User-Agent": api_headers["User-Agent"], # Consistent User-Agent
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

        logger.info(f"【{self.plugin_name}】'_fetch_jackett_indexers' CALLED. Host: {self._host}, API Key: {'[SET]' if self._api_key else '[NOT SET]'}")
        if not self._host or not self._api_key:
            logger.error(f"【{self.plugin_name}】Jackett Host 或 API Key 未配置，无法获取索引器。")
            return []
        
        host = self._host.rstrip('/')
        max_retries = 2 # We might not need many retries if the pre-request works
        retry_interval = 3 # Shorter interval
        current_try = 1
            
        # Headers for the actual API data request
        api_headers = {
            "User-Agent": f"MoviePilot-Plugin-{self.__class__.__name__}/{self.plugin_version}",
            "X-Api-Key": self._api_key,
            "Accept": "application/json, text/javascript, */*; q=0.01"
            # "Content-Type" is not strictly needed for a GET request to the indexers API
        }
        logger.debug(f"【{self.plugin_name}】API 请求头 (不含 Content-Type for GET): {api_headers}")

        # Create a session object to persist cookies
        with requests.Session() as session:
            # 1. Optional: Attempt password login if password is provided
            # This helps establish a strong session if successful.
            if self._password:
                login_url = f"{host}/UI/Login" # Common login submission URL, might vary slightly
                dashboard_check_url = f"{host}/UI/Dashboard" # To verify login
                
                # First, GET the login page to potentially get CSRF tokens or initial cookies (though Jackett might not use CSRF for login)
                try:
                    logger.info(f"【{self.plugin_name}】尝试GET登录页面: {login_url}")
                    session.get(login_url, verify=False, timeout=10) 
                    logger.info(f"【{self.plugin_name}】GET登录页面完成。当前Cookies: {session.cookies.get_dict()}")
                except requests.exceptions.RequestException as e:
                    logger.warn(f"【{self.plugin_name}】GET登录页面失败: {e}")

                # Then, POST to login
                login_payload = {
                    "username": "", # Jackett often doesn't use a username for its simple password auth
                    "password": self._password,
                    "rememberMe": "on" # Or "true", check Jackett's form
                }
                # Headers for POST login
                login_post_headers = {
                    "User-Agent": f"MoviePilot-Plugin-{self.__class__.__name__}/{self.plugin_version}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": login_url # Good practice to set referer for POSTs
                }
                try:
                    logger.info(f"【{self.plugin_name}】尝试用密码POST到登录URL: {login_url}")
                    # Jackett's actual login endpoint might be /UI/Dashboard directly with POST
                    # Or /api/v2.0/login, or /UI/Login. We'll try /UI/Login first as it's a common pattern.
                    # The original code used /UI/Dashboard for POST.
                    
                    # Let's try the original approach's target: /UI/Dashboard with password
                    login_submission_url = f"{host}/UI/Dashboard" # As per original code
                    logger.info(f"【{self.plugin_name}】尝试POST密码到: {login_submission_url}")

                    login_res = session.post(login_submission_url, data={"password": self._password}, headers=login_post_headers, verify=False, timeout=15, allow_redirects=True)
                    
                    logger.info(f"【{self.plugin_name}】密码登录POST响应状态: {login_res.status_code}. URL после POST: {login_res.url}")
                    logger.info(f"【{self.plugin_name}】密码登录后Cookies: {session.cookies.get_dict()}")

                    # A simple check: if we are redirected back to Login, it likely failed.
                    if "UI/Login" in login_res.url:
                        logger.warn(f"【{self.plugin_name}】密码登录后似乎仍停留在登录页，登录可能未成功。")
                    else:
                        logger.info(f"【{self.plugin_name}】密码登录POST似乎已完成（未重定向到登录页）。")
                        # Optionally, try a GET to dashboard to confirm session
                        # dashboard_get = session.get(dashboard_check_url, verify=False, timeout=10)
                        # logger.info(f"【{self.plugin_name}】访问Dashboard确认登录状态: {dashboard_get.status_code}, URL: {dashboard_get.url}")
                        # if "UI/Login" in dashboard_get.url:
                        #    logger.warn(f"【{self.plugin_name}】密码登录后访问Dashboard仍重定向到登录页。")

                except requests.exceptions.RequestException as e:
                    logger.error(f"【{self.plugin_name}】密码登录请求失败: {e}")
            else:
                # 2. If no password, or even if password login was attempted,
                #    make a "warm-up" GET request to a known Jackett page (e.g., its base URL or /UI/Dashboard).
                #    This is crucial if Jackett sets some session cookies even on unauthenticated visits
                #    or if the API key auth works better with an established session.
                warm_up_url = f"{host}/" # Try base URL or /UI/Dashboard
                try:
                    logger.info(f"【{self.plugin_name}】执行预热请求到: {warm_up_url}")
                    # Use a generic header for this, or let session use its defaults
                    session.get(warm_up_url, headers={"User-Agent": api_headers["User-Agent"]}, verify=False, timeout=10, allow_redirects=True)
                    logger.info(f"【{self.plugin_name}】预热请求完成。当前Cookies: {session.cookies.get_dict()}")
                except requests.exceptions.RequestException as e:
                    logger.warn(f"【{self.plugin_name}】预热请求失败: {e}")

            # 3. Now, attempt to get the actual API data using the (potentially cookie-populated) session
            #    and the X-Api-Key header.
            indexer_query_url = f"{host}/api/v2.0/indexers?configured=true"
            
            current_try = 1 # Reset retry counter for this specific operation
            while current_try <= max_retries:
                logger.info(f"【{self.plugin_name}】(使用Session) 请求Jackett索引器列表 (尝试 {current_try}/{max_retries}): {indexer_query_url}")
                try:
                    # IMPORTANT: Use the session object for the GET request and ensure API headers are used.
                    # session.headers should already have User-Agent if set globally,
                    # but X-Api-Key needs to be there. We'll merge api_headers into session headers.
                    
                    # Update session headers with specific API headers for this request
                    # This ensures X-Api-Key is present for this specific call
                    current_session_headers = session.headers.copy() # Get existing session headers (like cookies)
                    current_session_headers.update(api_headers)      # Add/override with our API specific headers
                    
                    logger.debug(f"【{self.plugin_name}】发送到API的最终请求头 (含 session cookies): {current_session_headers}")

                    response = session.get(indexer_query_url, headers=current_session_headers, verify=False, timeout=20)
                    
                    logger.info(f"【{self.plugin_name}】收到API响应状态: {response.status_code}")
                    logger.debug(f"【{self.plugin_name}】API响应头: {dict(response.headers)}")

                    if response.status_code == 200:
                        try:
                            # Check content type before trying to parse as JSON
                            content_type = response.headers.get('Content-Type', '').lower()
                            if 'application/json' in content_type:
                                indexers = response.json()
                                if indexers and isinstance(indexers, list):
                                    logger.info(f"【{self.plugin_name}】成功从Jackett获取到 {len(indexers)} 个索引器 (JSON)。")
                                    return indexers
                                else: # Empty list is also a valid JSON response
                                    logger.info(f"【{self.plugin_name}】从Jackett获取的索引器列表为空 (JSON)。")
                                    return [] 
                            else:
                                logger.error(f"【{self.plugin_name}】Jackett API响应Content-Type不是JSON: '{content_type}'. 响应码200但内容非预期。")
                                logger.error(f"【{self.plugin_name}】Jackett响应内容 (前500字符): {response.text[:500]}...")
                                # Treat as error, try again or fail
                        except json.JSONDecodeError as e:
                            logger.error(f"【{self.plugin_name}】解析Jackett API响应JSON失败: {e}")
                            logger.error(f"【{self.plugin_name}】Jackett响应内容 (前500字符): {response.text[:500]}...")
                    elif response.status_code == 302: # Explicitly handle 302
                        location = response.headers.get('Location', 'N/A')
                        logger.warn(f"【{self.plugin_name}】Jackett API请求被重定向 (302) 到: {location}. 这通常意味着认证问题或会话未建立。")
                    elif response.status_code in [401, 403]:
                        logger.error(f"【{self.plugin_name}】Jackett API认证或授权失败 (HTTP {response.status_code})。请检查API Key。")
                        # No point in retrying if it's an auth error with API key
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
        # This method is largely the same as before, focusing on fetching data
        # Removed print statements, relying on logger from the calling function or for specific errors here
        logger.info(f"【{self.plugin_name}】'_fetch_jackett_indexers' CALLED. Host: {self._host}, API Key: {'[SET]' if self._api_key else '[NOT SET]'}")
        if not self._host or not self._api_key: # Already checked by caller, but good for direct use
            logger.error(f"【{self.plugin_name}】Jackett Host 或 API Key 未配置，无法获取索引器。")
            return []
        
        host = self._host.rstrip('/')
        max_retries = 3
        retry_interval = 5
        current_try = 1
            
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": f"MoviePilot-Plugin-{self.__class__.__name__}/{self.plugin_version}",
            "X-Api-Key": self._api_key,
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }
        # Using a new session for each fetch operation to keep it simple
        with requests.Session() as session:
            session.headers.update(headers)
            # Password authentication for Jackett is primarily for UI.
            # API key should grant access to API endpoints.
            # If specific Jackett setups require cookie-based auth even for API after password login,
            # that would be a more complex scenario. Assuming API key is sufficient here.

            while current_try <= max_retries:
                try:
                    indexer_query_url = f"{host}/api/v2.0/indexers?configured=true"
                    logger.info(f"【{self.plugin_name}】请求Jackett索引器列表 (尝试 {current_try}/{max_retries}): {indexer_query_url}")
                    
                    response = session.get(indexer_query_url, verify=False, timeout=20)
                    
                    logger.debug(f"【{self.plugin_name}】Jackett响应状态: {response.status_code}")

                    if response.status_code == 200:
                        try:
                            indexers = response.json()
                            if indexers and isinstance(indexers, list):
                                logger.info(f"【{self.plugin_name}】成功从Jackett获取到 {len(indexers)} 个索引器。")
                                return indexers
                            else:
                                logger.warn(f"【{self.plugin_name}】从Jackett获取的索引器列表为空或格式无效. 响应体 (前200字符): {response.text[:200]}")
                                return [] 
                        except json.JSONDecodeError as e:
                            logger.error(f"【{self.plugin_name}】解析Jackett响应JSON失败: {e}")
                            logger.error(f"【{self.plugin_name}】Jackett响应内容 (前500字符): {response.text[:500]}...")
                            return [] 
                    elif response.status_code in [401, 403]:
                        logger.error(f"【{self.plugin_name}】Jackett认证或授权失败 (HTTP {response.status_code})。请检查API Key。响应体 (前200字符): {response.text[:200]}")
                        return [] 
                    else:
                        logger.warn(f"【{self.plugin_name}】从Jackett获取索引器列表失败: HTTP {response.status_code}. 响应体 (前200字符): {response.text[:200]}")
                    
                except requests.exceptions.Timeout:
                    logger.warn(f"【{self.plugin_name}】请求Jackett超时 (尝试 {current_try}/{max_retries}).")
                except requests.exceptions.RequestException as e:
                    logger.error(f"【{self.plugin_name}】请求Jackett网络异常 (尝试 {current_try}/{max_retries}): {e}")
                except Exception as e: 
                    logger.error(f"【{self.plugin_name}】获取Jackett索引器时发生未知错误 (尝试 {current_try}/{max_retries}): {e}", exc_info=True)
                
                if current_try < max_retries:
                    logger.info(f"【{self.plugin_name}】将在 {retry_interval} 秒后重试...")
                    time.sleep(retry_interval)
                current_try += 1

        logger.warn(f"【{self.plugin_name}】经过 {max_retries} 次尝试后，未能成功获取Jackett索引器列表。")
        return []

        # This method is identical to the one you provided previously.
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
                "id": mp_domain_id, "name": f"[Jackett] {indexer_name}", "domain": host, "url": host, "encoding": "UTF-8", "public": True, "proxy": True, "language": "zh_CN", "category": categories,
                "search": {"paths": [{"path": f"/api/v2.0/indexers/{indexer_id}/results/torznab", "method": "get"}], "params": {"t": "search", "q": "{keyword}", "cat": "{cat}", "apikey": self._api_key}},
                "torrents": {"list": {"selector": "item"}, "fields": {"title": {"selector": "title"}, "details": {"selector": "guid"}, "download": {"selector": "link"}, "size": {"selector": "size"}, "date_added": {"selector": "pubDate", "optional": True}, "seeders": {"selector": "torznab:attr[name=seeders]", "filters": [{"name": "re", "args": ["(\\d+)", 1]}], "default": "0"}, "leechers": {"selector": "torznab:attr[name=peers]", "filters": [{"name": "re", "args": ["(\\d+)", 1]}], "default": "0"}, "downloadvolumefactor": {"case": {"*": 0}}, "uploadvolumefactor": {"case": {"*": 1}}}}
            }
            # logger.debug(f"【{self.plugin_name}】格式化MoviePilot索引器配置完成: {mp_domain_id}") # Already logged by caller if successful
            return mp_indexer
        except Exception as e:
            logger.error(f"【{self.plugin_name}】格式化索引器 '{jackett_indexer.get('name', 'N/A')}' 失败: {e}", exc_info=True)
            return None

    def _format_indexer_for_moviepilot(self, jackett_indexer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            indexer_id_from_jackett = jackett_indexer.get("id", "") # e.g., "1337x"
            indexer_name_from_jackett = jackett_indexer.get("name", "")
            if not indexer_id_from_jackett or not indexer_name_from_jackett:
                logger.warn(f"【{self.plugin_name}】Jackett索引器数据不完整 (缺少ID或名称): {jackett_indexer}")
                return None

            # This is the internal ID MoviePilot will use, and also the "domain" part for the custom indexer plugin's string config.
            moviepilot_internal_id = f"jackett_{indexer_id_from_jackett.lower().replace('-', '_')}" 

            categories = { # Same as before
                "movie": [{"id": "2000", "desc": "Movies"}, {"id": "2010", "desc": "Movies/Foreign"}, {"id": "2020", "desc": "Movies/BluRay"}, {"id": "2030", "desc": "Movies/DVD"}, {"id": "2040", "desc": "Movies/HD"}, {"id": "2045", "desc": "Movies/UHD"}, {"id": "2050", "desc": "Movies/3D"}, {"id": "2060", "desc": "Movies/SD"}],
                "tv": [{"id": "5000", "desc": "TV"}, {"id": "5020", "desc": "TV/Blu-ray"}, {"id": "5030", "desc": "TV/DVD"}, {"id": "5040", "desc": "TV/HD"}, {"id": "5050", "desc": "TV/SD"}, {"id": "5060", "desc": "TV/Foreign"}, {"id": "5070", "desc": "TV/Sport"}]
            }
            
            actual_jackett_host = self._host.rstrip('/') # The real Jackett server address

            # This is the JSON object that will be base64 encoded
            mp_indexer_config_json = {
                # "id": This should be the unique identifier for MoviePilot's internal indexer management.
                # The Custom Indexer plugin uses the string before "|" as the primary key/domain.
                # The JSON itself also needs an "id". Let's keep them consistent.
                "id": moviepilot_internal_id,
                "name": f"[Jackett] {indexer_name_from_jackett}",
                
                # CRITICAL: These 'domain' and 'url' fields inside the JSON *must* point to the actual Jackett server.
                "domain": actual_jackett_host, 
                "url": actual_jackett_host,    
                
                "encoding": "UTF-8",
                "public": True, 
                "proxy": True, # Assuming proxy might be needed by MoviePilot to reach Jackett
                "language": "zh_CN", 
                "category": categories,
                "search": {
                    "paths": [
                        {
                            # This 'path' is relative to the 'domain'/'url' above (i.e., actual_jackett_host)
                            "path": f"/api/v2.0/indexers/{indexer_id_from_jackett}/results/torznab", 
                            "method": "get"
                        }
                    ],
                    "params": { # These params are appended to the search path
                        "t": "search",
                        "q": "{keyword}",
                        "cat": "{cat}",
                        "apikey": self._api_key # API key is passed as a query parameter to Jackett's torznab endpoint
                    }
                },
                "torrents": { # Torrents parsing rules, same as before
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
            return mp_indexer_config_json # Return the JSON object itself
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
        
        all_config_lines = [] # List to store all config lines
        output_count = 0

        for raw_indexer in raw_jackett_indexers:
            indexer_name = raw_indexer.get("name", "N/A")
            logger.debug(f"【{self.plugin_name}】正在处理Jackett索引器: {indexer_name}")
            
            # This mp_config_json is the actual JSON object for the indexer config
            mp_config_json_object = self._format_indexer_for_moviepilot(raw_indexer)
            
            if mp_config_json_object:
                try:
                    # The 'domain_part' for "domain|base64" string is the 'id' from the JSON object.
                    domain_part_for_custom_indexer = mp_config_json_object['id'] # e.g., "jackett_1337x"
                    
                    json_str_for_encoding = json.dumps(mp_config_json_object, ensure_ascii=False, indent=None)
                    base64_encoded_json = base64.b64encode(json_str_for_encoding.encode('utf-8')).decode('utf-8')
                    
                    custom_config_line = f"{domain_part_for_custom_indexer}|{base64_encoded_json}"
                    all_config_lines.append(custom_config_line)
                    output_count +=1
                    logger.debug(f"【{self.plugin_name}】为 '{indexer_name}' 生成配置行: {custom_config_line[:50]}...") # Log a snippet
                except Exception as e:
                    logger.error(f"【{self.plugin_name}】为索引器 '{indexer_name}' 生成Base64配置时出错: {e}", exc_info=True)
            else:
                logger.warn(f"【{self.plugin_name}】未能格式化索引器 '{indexer_name}' 的MoviePilot配置。")

        if all_config_lines:
            logger.info(f"【{self.plugin_name}】为 {output_count} 个Jackett索引器生成的“自定义索引站点”配置 (请将以下所有行复制到自定义索引站点插件中，每行一个):")
            logger.info(f"MOVIEPILOT_CUSTOM_INDEXER_CONFIG_BLOCK_START")
            for line in all_config_lines:
                logger.info(line) # Each config on its own line
            logger.info(f"MOVIEPILOT_CUSTOM_INDEXER_CONFIG_BLOCK_END")
            logger.info(f"【{self.plugin_name}】共 {output_count} 条配置已记录。")
        else:
            logger.warn(f"【{self.plugin_name}】虽然获取了原始索引器，但未能成功生成任何配置字符串。")
        logger.info(f"【{self.plugin_name}】Jackett索引器配置记录过程结束。")

        """
        获取Jackett索引器，格式化它们，并将配置字符串打印到日志。
        """
        logger.info(f"【{self.plugin_name}】开始获取Jackett索引器以生成配置字符串...")
        raw_jackett_indexers = self._fetch_jackett_indexers()

        if not raw_jackett_indexers:
            logger.warn(f"【{self.plugin_name}】未能从Jackett获取任何索引器，无法生成配置。请检查连接和Jackett设置。")
            return

        logger.info(f"【{self.plugin_name}】成功获取 {len(raw_jackett_indexers)} 个原始索引器。开始格式化并记录配置...")
        
        output_count = 0
        for raw_indexer in raw_jackett_indexers:
            indexer_name = raw_indexer.get("name", "N/A")
            logger.info(f"【{self.plugin_name}】正在处理Jackett索引器: {indexer_name}")
            mp_config_json = self._format_indexer_for_moviepilot(raw_indexer)
            if mp_config_json:
                try:
                    domain_part = mp_config_json['id'] 
                    json_str = json.dumps(mp_config_json, ensure_ascii=False, indent=None) # indent=None for single line
                    base64_encoded_json = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                    custom_config_line = f"{domain_part}|{base64_encoded_json}"
                    
                    # Log the output clearly for the user
                    logger.info(f"【{self.plugin_name}】自定义索引站点配置 for '{indexer_name}' (ID: {domain_part}):")
                    logger.info(f"MOVIEPILOT_CUSTOM_INDEXER_CONFIG_START\n{custom_config_line}\nMOVIEPILOT_CUSTOM_INDEXER_CONFIG_END")
                    output_count +=1
                except Exception as e:
                    logger.error(f"【{self.plugin_name}】为索引器 '{indexer_name}' 生成Base64配置时出错: {e}", exc_info=True)
            else:
                logger.warn(f"【{self.plugin_name}】未能格式化索引器 '{indexer_name}' 的MoviePilot配置。")

        if output_count > 0:
            logger.info(f"【{self.plugin_name}】成功为 {output_count} 个Jackett索引器生成并记录了配置字符串。请从上面的日志中复制它们（在 MOVIEPILOT_CUSTOM_INDEXER_CONFIG_START 和 MOVIEPILOT_CUSTOM_INDEXER_CONFIG_END 之间）。")
        else:
            logger.warn(f"【{self.plugin_name}】虽然获取了原始索引器，但未能成功生成任何配置字符串。")
        logger.info(f"【{self.plugin_name}】Jackett索引器配置记录过程结束。")

    def get_form(self) -> Tuple[List[dict], dict]:
        """
        获取配置表单 (保持不变，用户仍需通过这里配置Jackett信息和启用插件)
        """
        return [
            {'component': 'VAlert', 'props': {'type': 'info', 'text': '启用并配置Jackett服务器信息后，插件会自动获取Jackett中的索引器，并将其“自定义索引站点”配置字符串输出到MoviePilot的日志中。您需要从日志中复制这些配置。', 'class': 'mb-4'}},
            {'component': 'VSwitch', 'props': {'model': 'enabled', 'label': '启用插件'}},
            {'component': 'VTextField', 'props': {'model': 'host', 'label': 'Jackett地址', 'placeholder': 'http://localhost:9117', 'hint': '请输入Jackett的完整地址，包括http或https前缀。'}},
            {'component': 'VTextField', 'props': {'model': 'api_key', 'label': 'API Key', 'type': 'password', 'placeholder': 'Jackett管理界面右上角的API Key'}},
            {'component': 'VTextField', 'props': {'model': 'password', 'label': 'Jackett管理密码 (可选)', 'type': 'password', 'placeholder': 'Jackett管理界面配置的Admin password，如未配置可为空。API Key通常已足够。'}},
            # 添加一个按钮，允许用户手动触发日志输出，以防初始化时失败或需要重新生成
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
                        # 调用一个简单的API来触发后端的 log_jackett_indexer_configs 方法
                        'value': "() => { this.$axios.get('/api/v1/plugin/Jackett/jackett/trigger_log_configs').then(res => this.$toast.info(res.data.message || '操作完成，请查看日志。')).catch(err => this.$toast.error('触发日志记录失败: ' + (err.response?.data?.message || err.message))); }"
                    }
                ]
            }
        ], {"enabled": False, "host": "", "api_key": "", "password": ""}

    def get_state(self) -> bool:
        return self._enabled

    def stop_service(self) -> None:
        logger.info(f"【{self.plugin_name} ({self.__class__.__name__})】插件服务已停止。")

    # 移除 get_page，因为不再需要复杂的自定义UI页面
    def get_page(self) -> Optional[List[dict]]:
        return None # 或者 return []

    # 添加一个简单的API来手动触发日志记录
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