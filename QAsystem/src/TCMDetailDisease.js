import React from 'react';
import { useParams } from 'react-router-dom';
import './TCMDetail.css';

const diseaseDetails = {
  '蝎鳌痛': {
    overview: '蝎子蛰伤会很痛，但很少会危及生命。健康的成人通常不需要治疗蝎子蛰伤。幼童和老年人最容易出现严重并发症。',
    description: `
      蝎子为节肢动物，是昆虫、蜘蛛和甲壳类动物的近亲。树皮蝎是美国唯一一种毒液强到足以引起严重症状的蝎子，通常长约 1.6 至 3 英寸（4 至 8 厘米），包括一条分节的尾巴，其尾部毒刺可释放毒液。蝎子主要生活在西南部的沙漠。全世界约有 2000 种蝎子，其中只有约 100 种能产生足以致命的毒液。
      蝎子有八条腿、一对与龙虾类似的钳夹，以及一条向上弯曲的尾巴。蝎子通常在夜间较为活跃。除非受到挑衅或攻击，否则一般不会蜇人。大多数蝎子蜇伤发生在意外抓取、踩到或身体触碰到蝎子时。
    `,
    symptoms: `
      蝎子蛰伤部位的常见症状可能包括：
      - 疼痛，可能很严重。
      - 麻木感和刺痛感。
      - 轻微肿胀。
      - 温热。

      毒液累及全身（通常见于被蜇伤的儿童）的症状包括：
      - 呼吸困难。
      - 肌肉抽搐或肌肉抖动。
      - 头部、颈部和眼球运动不正常。
      - 流口水。
      - 出汗。
      - 言语不清。
      - 恶心和呕吐。
      - 高血压（高血压症）。
      - 心率加快（心动过速）。
      - 烦躁不安或易激动，或患儿哭闹无法安抚。
    `,
    complications: `
      年长者和幼童最有可能死于未经治疗的有毒蝎子螫伤，因为螫伤后数小时通常会发生心力衰竭或呼吸衰竭。在美国，很少有蝎子螫伤致死的报道。
      极少数情况下，蝎子螫伤可能会导致严重过敏反应。
    `,
    prevention: `
      - 移开房子周围的石堆或木材堆，不要把柴火挨着房子放置或放在屋内。
      - 草坪修剪齐短，修剪灌木和悬垂的树枝，切除让蝎子可以通往屋顶的路径。
      - 填补裂缝，门窗周围安装挡雨条，修补破损的纱窗。
      - 检查并抖抖一段时间未使用的园艺手套、衣服和靴子。
      - 当您旅行时，请采取一些措施。如果身处致命性蝎子的常见地区，尤其是在露营或居处简陋时，要穿好鞋子。也要经常抖抖自己的衣服、床上用品、装备和包裹。
    `
  }
};

const TCMDetailDisease = () => {
  const { name } = useParams();
  const details = diseaseDetails[name] || {};

  return (
    <div className="tcm-detail-container">
      <h1>{name}</h1>
      <p><strong>概述：</strong>{details.overview}</p>
      <p><strong>描述：</strong>{details.description}</p>
      <p><strong>症状：</strong>{details.symptoms}</p>
      <p><strong>并发症：</strong>{details.complications}</p>
      <p><strong>预防：</strong>{details.prevention}</p>
    </div>
  );
};

export default TCMDetailDisease;
