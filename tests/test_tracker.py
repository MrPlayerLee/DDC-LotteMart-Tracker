import unittest

from tracker import (
    declared_empty, find_store, number_from_price, parse_products, parse_stores,
    stock_status, total_pages, volume,
)


class ParserTests(unittest.TestCase):
    def test_store_discovery(self):
        html = '<option value="">매장선택</option><option value="1234">동두천점</option>'
        self.assertEqual(parse_stores(html), {"동두천점": "1234"})
        self.assertEqual(find_store(parse_stores(html), "동두천점"), "1234")

    def test_product_parser_and_unknown_discount(self):
        html = """
        <script>var totalPage = 2;</script>
        <li><div class="layer_popup">
          <div class="layer-head">조니워커 블랙라벨 70cl</div>
          <table>
            <tr><th>ㆍ 규격 :</th><td>70cl</td></tr>
            <tr><th>ㆍ 가격 :</th><td>38,500원</td></tr>
            <tr><th>ㆍ 재고 :</th><td>품절</td></tr>
          </table>
        </div></li>
        """
        parsed = parse_products(html)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["volume"], "700mL")
        self.assertEqual(parsed[0]["price_krw"], 38500)
        self.assertEqual(parsed[0]["stock_status"], "out_of_stock")
        self.assertEqual(parsed[0]["discount_status"], "unknown")
        self.assertIsNone(parsed[0]["discount_rate_pct"])
        self.assertEqual(total_pages(html), 2)

    def test_explicit_regular_price(self):
        html = """
        <div class="layer_popup">
          <div class="layer-head">테스트상품 500ml</div>
          <table>
            <tr><th>ㆍ 정상가 :</th><td>30,000원</td></tr>
            <tr><th>ㆍ 가격 :</th><td>20,000원</td></tr>
            <tr><th>ㆍ 재고 :</th><td>4개</td></tr>
          </table>
        </div>
        """
        product = parse_products(html)[0]
        self.assertEqual(product["discount_status"], "discounted")
        self.assertEqual(product["stock_status"], "in_stock")
        self.assertEqual(product["discount_rate_pct"], 33.33)
        stated = html.replace("정상가", "할인율").replace("30,000원", "15%")
        self.assertEqual(parse_products(stated)[0]["discount_rate_pct"], 15)

    def test_explicit_zero_count(self):
        html = '<section class="result-prod"><div class="total-num">검색결과 : <span>0</span>건</div></section>'
        self.assertTrue(declared_empty(html))
        self.assertFalse(declared_empty(html.replace(">0<", ">10<")))
        self.assertFalse(declared_empty("<html></html>"))

    def test_unknown_not_sold_out(self):
        self.assertEqual(stock_status(None), "unknown")
        self.assertEqual(stock_status("확인 중"), "unknown")
        self.assertEqual(stock_status("0"), "out_of_stock")
        self.assertEqual(stock_status("12병"), "in_stock")

    def test_price_and_volume(self):
        self.assertEqual(number_from_price("31,500원"), 31500)
        self.assertIsNone(number_from_price("가격 미확인"))
        self.assertEqual(volume("서울우유", "1,000ML"), "1000mL")
        self.assertEqual(volume("조니워커", "1L"), "1000mL")
        self.assertEqual(volume("조니워커 50cl", ""), "500mL")


if __name__ == "__main__":
    unittest.main()
