const assert=require('node:assert/strict');
const {metrics,filter}=require('../payments/metrics.js');
const base={psp:'PSP1',country:'MX',method:'credit_card',currency:'MXN',timestamp:'2026-09-01T00:00:00Z'};
const rows=[
 {...base,id:'1',status:'approved',amount_minor:10000,fee_minor:300},
 {...base,id:'2',status:'declined',amount_minor:10000,fee_minor:10},
 {...base,id:'3',status:'pending',amount_minor:5000,fee_minor:null},
 {...base,id:'4',status:'refunded',amount_minor:20000,fee_minor:600},
 {...base,id:'5',status:'approved',amount_minor:30000,fee_minor:null},
 {...base,id:'6',country:'BR',currency:'BRL',method:'pix',status:'approved',amount_minor:50000,fee_minor:100}
];
const m=metrics(rows), mx=m.currencies.find(r=>r.currency==='MXN');
assert.equal(m.authorization,.75);assert.equal(m.success,.8);assert.equal(m.cardDecisions,4);
assert.equal(mx.tpv,60000);assert.equal(mx.refunds,20000);assert.equal(mx.net,40000);
assert.equal(mx.effectiveRate,.03);assert.equal(mx.feePerPaid,450);assert.equal(mx.coverage,2/3);assert.equal(mx.allKnownFees,910);
assert.equal(m.currencies.length,2);assert.equal(metrics([]).authorization,null);
assert.equal(metrics(rows.filter(r=>r.method==='pix')).authorization,null);
assert.equal(filter(rows,{country:'BR',psp:'PSP1',method:'pix',start:'2026-09-01',end:'2026-09-01'}).length,1);
assert.equal(filter(rows,{start:'2026-09-02'}).length,0);
assert.equal(metrics([{...base,status:'approved',amount_minor:100,fee_minor:0}]).currencies[0].effectiveRate,0);
console.log('Metric checks passed: denominators, refunds, currencies, fee coverage, zero fees and all filters.');
