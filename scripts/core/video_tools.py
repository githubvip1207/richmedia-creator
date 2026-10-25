"""The video API web-search tool currently verified for Volcengine only."""
from .request import require


def validate_video_tools(provider, operation, tools):
    require(provider == 'volcengine' and operation in ('text-to-video', 'image-to-video'),
            'Video tools are implemented only for Volcengine text-to-video and image-to-video')
    require(isinstance(tools, list) and (tools == [] or tools == [{'type': 'web_search'}]),
            'Video tools must be [] or [{"type":"web_search"}]')
