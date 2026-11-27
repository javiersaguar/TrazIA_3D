"use client";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { API_BASE } from "@/lib/api/config";
import type { ProcessAdjustment } from "@/lib/api/client";

export const useQuestions = create<{values:Record<string,string>;set:(key:string,value:string)=>void}>()(persist(set=>({
  values:{},set:(key,value)=>set(s=>({values:{...s.values,[key]:value}})),
}),{name:"trazia-copilot-questions",storage:createJSONStorage(()=>({
  getItem:key=>{try{return sessionStorage.getItem(key);}catch{return null;}},
  setItem:(key,value)=>{try{sessionStorage.setItem(key,value);}catch{/* memoria */}},
  removeItem:key=>{try{sessionStorage.removeItem(key);}catch{/* memoria */}},
})),partialize:s=>({values:s.values})}));

export function useQuestion(revision:string,path?:string){
  const key=JSON.stringify([API_BASE,revision,path??"equipo"]);
  const value=useQuestions(s=>s.values[key]??"");
  const set=useQuestions(s=>s.set);
  return [value,(value:string)=>set(key,value)] as const;
}

export const useProcessCopilotDraft = create<{
  pending: { project: string; revision: "A" | "B"; adjustments: ProcessAdjustment[] } | null;
  setPending: (pending: { project: string; revision: "A" | "B"; adjustments: ProcessAdjustment[] } | null) => void;
}>()(set => ({ pending: null, setPending: pending => set({ pending }) }));
