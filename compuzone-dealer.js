(() => {
  const priceTable = document.querySelector("#ssdTableArea");
  if (!priceTable || document.querySelector("#compuzone-dealer-price")) return;

  const card = document.createElement("section");
  card.id = "compuzone-dealer-price";
  card.style.cssText = "margin:12px 0;padding:12px;border:1px solid #d9e3e7;border-radius:12px";
  const title = document.createElement("strong");
  title.textContent = "컴퓨존 870 EVO 2TB";
  const prices = document.createElement("p");
  prices.style.margin = "5px 0";
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
    const record = await response.json();
    const observed = new Date(record.observed_at);
    if (record.product_no !== "755256" || !validPrice(record.displayed_benefit_price_ex_vat_krw)
        || !Number.isFinite(observed.getTime())) throw new Error();
    prices.textContent = "판매가 " + displayWon(record.sale_price_ex_vat_krw)
      + " · 표시 혜택가 " + displayWon(record.displayed_benefit_price_ex_vat_krw);
    status.textContent = "부가세 별도 · 확인 " + clock.format(observed) + " KST · 상품 화면 표시가";
  }

  loadDealerPrice().catch(() => {
    status.textContent = "컴퓨존 혜택가를 불러오지 못했습니다.";
  });
})();
