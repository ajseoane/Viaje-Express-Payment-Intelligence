/* Pure metric functions shared by the dashboard and Node-based verification. */
(function(root) {
  const settled = r => ['approved','refunded'].includes(r.status);
  const decided = r => ['approved','refunded','declined'].includes(r.status);
  const card = r => ['credit_card','debit_card'].includes(r.method);
  const sum = (rows, f) => rows.reduce((s,r) => s+f(r), 0);
  const ratio = (a,b) => b ? a/b : null;
  function metrics(rows) {
    const decisions=rows.filter(decided), cards=decisions.filter(card);
    const paid=rows.filter(settled), covered=paid.filter(r=>r.fee_minor!==null);
    return {count:rows.length, decisions:decisions.length,
      cardDecisions:cards.length, cardApproved:cards.filter(settled).length,
      authorization:ratio(cards.filter(settled).length,cards.length),
      success:ratio(decisions.filter(settled).length,decisions.length),
      currencies:[...new Set(rows.map(r=>r.currency))].sort().map(currency=>{
        const all=rows.filter(r=>r.currency===currency), gross=paid.filter(r=>r.currency===currency), known=covered.filter(r=>r.currency===currency);
        const tpv=sum(gross,r=>r.amount_minor), refunds=sum(all.filter(r=>r.status==='refunded'),r=>r.amount_minor);
        const fees=sum(known,r=>r.fee_minor), basis=sum(known,r=>r.amount_minor);
        return {currency,tpv,refunds,net:tpv-refunds,fees,basis,effectiveRate:ratio(fees,basis),
          feePerPaid:ratio(fees,known.length),coverage:ratio(known.length,gross.length),
          knownCount:known.length,paidCount:gross.length,
          allKnownFees:sum(all,r=>r.fee_minor??0)};
      })};
  }
  function filter(rows, f) {
    return rows.filter(r=>(!f.start||r.timestamp.slice(0,10)>=f.start)&&(!f.end||r.timestamp.slice(0,10)<=f.end)&&
      (!f.country||r.country===f.country)&&(!f.psp||r.psp===f.psp)&&(!f.method||r.method===f.method));
  }
  function groups(rows, keys) {
    const grouped=new Map();
    rows.forEach(r=>{const key=keys.map(k=>r[k]).join(' / '); if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(r);});
    return [...grouped].sort((a,b)=>a[0].localeCompare(b[0]));
  }
  const api={metrics,filter,groups,settled,decided,card};
  if(typeof module!=='undefined'&&module.exports) module.exports=api;
  root.PaymentMetrics=api;
})(typeof globalThis!=='undefined'?globalThis:this);
