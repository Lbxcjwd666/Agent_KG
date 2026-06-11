import React from 'react';
import { useParams } from 'react-router-dom';
import './TCMDetail.css';

const acupunctureDetails = {
  '睛明穴': {
    function: '降温除浊。',
    anatomy: '在眶内缘睑内侧韧带中，深部为眼内直肌；有内眦动、静脉和滑车上下动、静脉，深层上方有眼动、静脉本干；布有滑车上、下神经，深层为眼神经，上方为鼻睫神经。',
    indications: '1. 目赤肿痛、目眩、近视等目疾；2. 急性腰扭伤；3. 心动过速。',
    clinicalApplication: '现代常用于治疗视神经炎、结膜炎、急性腰扭伤等。配合谷、四白主治目生翳膜；',
    efficacy: '泄热明目，祛风通络。',
    notes: '手足太阳、足阳明、阴跷、阳跷五脉交会穴。',
    relatedDiscussion: `
      《甲乙经》：“手足太阳、足阳明之会。”
      《铜人》：“治攀睛，翳膜覆瞳子”
      《大成》：“主目远视不明，恶风流泪......小儿疳积，大人气眼冷泪。”
    `
  }
};

const TCMDetailAcupuncture = () => {
  const { name } = useParams();
  const details = acupunctureDetails[name] || {};

  return (
    <div className="tcm-detail-container">
      <h1>{name}</h1>
      <p><strong>功能作用：</strong>{details.function}</p>
      <p><strong>解剖：</strong>{details.anatomy}</p>
      <p><strong>主治：</strong>{details.indications}</p>
      <p><strong>临床运用：</strong>{details.clinicalApplication}</p>
      <p><strong>功效：</strong>{details.efficacy}</p>
      <p><strong>附注：</strong>{details.notes}</p>
      <p><strong>相关论述：</strong>{details.relatedDiscussion}</p>
    </div>
  );
};

export default TCMDetailAcupuncture;
