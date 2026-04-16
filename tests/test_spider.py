import pytest

from src.spider import BeautyRankingSpider


class FakeResponse:
    def __init__(self, status=200, text=""):
        self.status = status
        self.text = text


class TestIsBlocked:
    def setup_method(self):
        self.spider = BeautyRankingSpider.__new__(BeautyRankingSpider)

    @pytest.mark.asyncio
    async def test_status_403(self):
        resp = FakeResponse(status=403)
        assert await self.spider.is_blocked(resp) is True

    @pytest.mark.asyncio
    async def test_status_500(self):
        resp = FakeResponse(status=500)
        assert await self.spider.is_blocked(resp) is True

    @pytest.mark.asyncio
    async def test_blocked_message(self):
        resp = FakeResponse(status=200, text="페이지가 정상 동작하지 않습니다")
        assert await self.spider.is_blocked(resp) is True

    @pytest.mark.asyncio
    async def test_normal_response(self):
        resp = FakeResponse(status=200, text="<html>정상 페이지</html>")
        assert await self.spider.is_blocked(resp) is False

    @pytest.mark.asyncio
    async def test_none_status(self):
        resp = FakeResponse(status=None, text="")
        assert await self.spider.is_blocked(resp) is False
