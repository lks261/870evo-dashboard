(() => {
  const priceTable = document.querySelector("#ssdTableArea");
  if (!priceTable || document.querySelector("#compuzone-dealer-price")) return;

  const card = document.createElement("section");
  card.id = "compuzone-dealer-price";
  card.style.cssText = "margin:12px 0;padding:12px;border:1px solid #d9e3e7;border-radius:12px";
  const title = document.createElement("strong");
  title.textContent = "컴퓨존 870 EVO 용량별 혜택가";
  const prices = document.createElement("div");
  prices.style.cssText = "margin:5px 0;overflow-x:auto";
  const status = document.createElement("small");
  status.textContent = "게시된 혜택가를 확인하는 중입니다.";
  card.append(title, prices, status);
  priceTable.after(card);

  const won = new Intl.NumberFormat("ko-KR");
  const clock = new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Seoul",
  });
  const validPrice = (price) => Number.isSafeInteger(price) && price > 0;
  const displayWon = (price) => validPrice(price) ? won.format(price) + "원" : "확인 불가";

  async function loadDealerPrice() {
    const response = await fetch("./data/ssd/compuzone_dealer.json", { cache: "no-store" });
    if (response.status === 404) {
      status.textContent = "게시된 컴퓨존 혜택가가 없습니다.";
      return;
    }
    if (!response.ok) throw new Error();
    const data = await response.json();
    const items = data.items ?? [{ ...data, capacity: "2TB" }];
    const products = { "250GB": "755258", "500GB": "755259", "1TB": "755257",
      "2TB": "755256", "4TB": "755255", "8TB": "1325879" };
    const records = new Map(items.filter((item) => item && Object.hasOwn(products, item.capacity)
      && item.product_no === products[item.capacity] && Number.isFinite(Date.parse(item.observed_at)))
      .map((item) => [item.capacity, item]));
    const table = document.createElement("table");
    const head = table.createTHead().insertRow();
    for (const titleText of ["용량", "판매가", "표시 혜택가", "확인 시각"]) {
      const header = document.createElement("th");
      header.scope = "col";
      header.textContent = titleText;
      head.append(header);
    }
    const body = table.createTBody();
    for (const capacity of Object.keys(products)) {
      const item = records.get(capacity);
      const row = body.insertRow();
      const values = [capacity, item ? displayWon(item.sale_price_ex_vat_krw) : "—",
        item ? displayWon(item.displayed_benefit_price_ex_vat_krw) : "—",
        item ? clock.format(new Date(item.observed_at)) : "—"];
      for (const value of values) row.insertCell().textContent = value;
    }
    prices.append(table);
    status.textContent = "부가세 별도 · 한국시간 · 상품 화면 표시가";
  }

  loadDealerPrice().catch(() => {
    status.textContent = "컴퓨존 혜택가를 불러오지 못했습니다.";
  });
})();
