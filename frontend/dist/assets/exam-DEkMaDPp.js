import{B as s}from"./index-CycXevKq.js";const r=t=>s.post("/exam/start",t),m=(t,e)=>s.post("/exam/submit",{session_id:t,answers:e}),o=t=>s.get(`/exam/result/${t}`);export{m as a,o as g,r as s};
