import React, { useState, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import TinyPinyin from 'tiny-pinyin';
import './TCMPage.css';
import data from './data';

const TCMPage = () => {
  const { type } = useParams();
  const navigate = useNavigate();
  const [selectedLetter, setSelectedLetter] = useState('全部');
  const [currentPage, setCurrentPage] = useState(1);
  const [searchTerm, setSearchTerm] = useState('');
  const itemsPerPage = 20;

  useEffect(() => {
    console.log('Global Data:', data); // 调试输出
  }, []);

  const handleLetterClick = (letter) => {
    setSelectedLetter(letter);
    setCurrentPage(1);
  };

  const handleItemClick = (item) => {
    const { name, type } = item;
    navigate(`/tcm/${type === 'DIS' ? 'DISEASE' : type}-detail/${name}`);
  };

  const typeData = data[type] || [];

  const filteredData = typeData.filter(item => {
    const matchesSearchTerm = item.name.includes(searchTerm);
    const matchesLetter = selectedLetter === '全部' || TinyPinyin.convertToPinyin(item.name[0]).charAt(0).toUpperCase() === selectedLetter;
    return matchesSearchTerm && matchesLetter;
  });

  console.log('Filtered Data for type:', type, filteredData); // 调试输出

  const totalPages = Math.ceil(filteredData.length / itemsPerPage);

  const paginatedData = filteredData.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  useEffect(() => {
    console.log('Paginated Data:', paginatedData); // 调试输出
  }, [paginatedData]);

  const renderPagination = () => {
    const pageNumbers = [];
    const maxPageButtons = 7;

    if (totalPages <= maxPageButtons) {
      for (let i = 1; i <= totalPages; i++) {
        pageNumbers.push(i);
      }
    } else {
      const startPage = Math.max(2, currentPage - 2);
      const endPage = Math.min(totalPages - 1, currentPage + 2);

      pageNumbers.push(1);
      if (startPage > 2) {
        pageNumbers.push('...');
      }

      for (let i = startPage; i <= endPage; i++) {
        pageNumbers.push(i);
      }

      if (endPage < totalPages - 1) {
        pageNumbers.push('...');
      }

      pageNumbers.push(totalPages);
    }

    return pageNumbers.map((number, index) => (
      <span
        key={index}
        onClick={() => typeof number === 'number' && setCurrentPage(number)}
        className={currentPage === number ? 'active' : ''}
        style={{ cursor: typeof number === 'number' ? 'pointer' : 'default' }}
      >
        {number}
      </span>
    ));
  };

  return (
    <div className="tcm-container">
      <header className="tcm-header">
        <nav className="tcm-nav">
          <Link to="/tcm/DIS">疾病</Link>
          <Link to="/tcm/herbs">中药材</Link>
          <Link to="/tcm/formulas">中药方剂</Link>
          <Link to="/tcm/acupuncture">穴位信息</Link>
        </nav>
      </header>
      <div className="tcm-content">
        <h2>
          {type === 'DIS' ? '疾病'
            : type === 'herbs' ? '中药材'
            : type === 'formulas' ? '中药方剂'
            : type === 'acupuncture' ? '穴位信息'
            : ''}
        </h2>
        <div className="search-container">
          <input
            type="text"
            placeholder="搜索..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="search-input"
          />
        </div>
        <div className="alphabet">
          <span
            onClick={() => handleLetterClick('全部')}
            className={selectedLetter === '全部' ? 'active' : ''}
          >
            全部
          </span>
          {Array.from({ length: 26 }, (_, i) => {
            const letter = String.fromCharCode(65 + i);
            const isDisabled = !typeData.some(
              item =>
                TinyPinyin.convertToPinyin(item.name[0]).charAt(0).toUpperCase() === letter
            );
            return (
              <span
                key={i}
                onClick={() => !isDisabled && handleLetterClick(letter)}
                className={`${selectedLetter === letter ? 'active' : ''} ${isDisabled ? 'disabled' : ''}`}
              >
                {letter}
              </span>
            );
          })}
        </div>
        <div className="item-list fixed-height">
          {paginatedData.length === 0 ? (
            <div className="no-item">暂无记录</div>
          ) : (
            paginatedData.map((item, index) => (
              <div key={index} className="item" onClick={() => handleItemClick(item)}>
                {item.name}
              </div>
            ))
          )}
        </div>
        {totalPages > 1 && (
          <div className="pagination">
            {renderPagination()}
          </div>
        )}
      </div>
    </div>
  );
};

export default TCMPage;
