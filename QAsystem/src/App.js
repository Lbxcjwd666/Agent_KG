import React, { lazy, Suspense } from 'react';
import './App.css';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import QuestionAnswer from './QuestionAnswer';
import { DataProvider } from './DataContext';

const TCMPage = lazy(() => import('./TCMPage'));
const TCMDetailDisease = lazy(() => import('./TCMDetailDisease'));
const TCMDetailFormula = lazy(() => import('./TCMDetailFormula'));
const TCMDetailHerb = lazy(() => import('./TCMDetailHerb'));
const TCMDetailAcupuncture = lazy(() => import('./TCMDetailAcupuncture'));

function PageShell({ title, children }) {
    return (
        <>
            <header className="App-header">
                <h1>{title}</h1>
            </header>
            <main>
                <Suspense fallback={<div className="page-loading">加载中...</div>}>
                    {children}
                </Suspense>
            </main>
        </>
    );
}

function App() {
    return (
        <DataProvider>
            <Router>
                <div className="App">
                    <Routes>
                        <Route path="/" element={
                            <PageShell title="基于知识增强的中医语言模型临床决策支持问答系统">
                                <QuestionAnswer />
                            </PageShell>
                        } />
                        <Route path="/tcm/:type" element={
                            <PageShell title="中医资源">
                                <TCMPage />
                            </PageShell>
                        } />
                        <Route path="/tcm/DISEASE-detail/:name" element={
                            <PageShell title="中医疾病详情">
                                <TCMDetailDisease />
                            </PageShell>
                        } />
                        <Route path="/tcm/formulas-detail/:name" element={
                            <PageShell title="中医方剂详情">
                                <TCMDetailFormula />
                            </PageShell>
                        } />
                        <Route path="/tcm/herbs-detail/:name" element={
                            <PageShell title="中药材详情">
                                <TCMDetailHerb />
                            </PageShell>
                        } />
                        <Route path="/tcm/acupuncture-detail/:name" element={
                            <PageShell title="穴位信息详情">
                                <TCMDetailAcupuncture />
                            </PageShell>
                        } />
                    </Routes>
                </div>
            </Router>
        </DataProvider>
    );
}

export default App;
