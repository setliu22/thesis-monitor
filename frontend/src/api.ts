export async function api<T>(path:string,method='GET',body?:unknown):Promise<T>{
 const response=await fetch('/api'+path,{method,headers:body===undefined?{}:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
 const data=await response.json();
 if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Please check your inputs and try again.');
 return data as T;
}
export const labels:Record<string,string>={revenue:'Revenue',revenue_growth:'Revenue growth',operating_income:'Operating income',operating_margin:'Operating margin',operating_cash_flow:'Operating cash flow',cash_flow_growth:'Cash flow growth',capital_expenditures:'Capital expenditures',free_cash_flow:'Free cash flow',debt:'Long-term debt'};
export const operators:Record<string,string>={lt:'below',lte:'at or below',gt:'above',gte:'at or above'};
export function format(value:string|null|undefined,unit='USD'){
 if(value==null)return '—';
 const n=Number(value);if(!Number.isFinite(n))return '—';
 if(unit==='%')return n.toFixed(1)+'%';
 return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',notation:'compact',maximumFractionDigits:2}).format(n);
}
export function date(value:string|null|undefined){return value?new Date(value.length===10?value+'T12:00:00Z':value).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}):'Not synced yet';}
