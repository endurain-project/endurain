import { describe, it, expect } from 'vitest';
import { DateTime } from 'luxon';
import {
  getWeekStartDate,
  getWeekEndDate,
  navigateWeek,
  formatDateISO
} from '@/utils/dateUtils';

describe('Date Utils - Week Navigation and Boundaries', () => {
  
  describe('getWeekStartDate', () => {
    it('should return Sunday as start of week when firstDayOfWeek is 0 (Sunday)', () => {
      // Test with Wednesday, March 15, 2025
      const inputDate = new Date(2025, 2, 15); // March 15, 2025 (Wednesday)
      const result = getWeekStartDate(inputDate, 0);
      
      // Expected: Sunday, March 12, 2025
      expect(formatDateISO(result)).toBe('2025-03-12');
    });

    it('should return Monday as start of week when firstDayOfWeek is 1 (Monday)', () => {
      // Test with Wednesday, March 15, 2025
      const inputDate = new Date(2025, 2, 15); // March 15, 2025 (Wednesday)
      const result = getWeekStartDate(inputDate, 1);
      
      // Expected: Monday, March 13, 2025
      expect(formatDateISO(result)).toBe('2025-03-13');
    });

    it('should return Tuesday as start of week when firstDayOfWeek is 2 (Tuesday)', () => {
      // Test with Wednesday, March 15, 2025
      const inputDate = new Date(2025, 2, 15); // March 15, 2025 (Wednesday)
      const result = getWeekStartDate(inputDate, 2);
      
      // Expected: Tuesday, March 14, 2025
      expect(formatDateISO(result)).toBe('2025-03-14');
    });

    it('should handle edge case when input date is already the first day of week', () => {
      // Test with Sunday when firstDayOfWeek is 0
      const inputDate = new Date(2025, 2, 12); // March 12, 2025 (Sunday)
      const result = getWeekStartDate(inputDate, 0);
      
      // Expected: Same Sunday
      expect(formatDateISO(result)).toBe('2025-03-12');
    });

    it('should handle edge case when input date is already the first day of week (Monday)', () => {
      // Test with Monday when firstDayOfWeek is 1
      const inputDate = new Date(2025, 2, 13); // March 13, 2025 (Monday)
      const result = getWeekStartDate(inputDate, 1);
      
      // Expected: Same Monday
      expect(formatDateISO(result)).toBe('2025-03-13');
    });

    it('should handle month boundaries correctly', () => {
      // Test with first day of month when week started in previous month
      const inputDate = new Date(2025, 3, 1); // April 1, 2025 (Saturday)
      const result = getWeekStartDate(inputDate, 0); // Sunday start
      
      // Expected: Sunday, March 26, 2025
      expect(formatDateISO(result)).toBe('2025-03-26');
    });

    it('should handle year boundaries correctly', () => {
      // Test with first day of year when week started in previous year
      const inputDate = new Date(2025, 0, 1); // January 1, 2025 (Sunday)
      const result = getWeekStartDate(inputDate, 1); // Monday start
      
      // Expected: Monday, December 26, 2025
      expect(formatDateISO(result)).toBe('2025-12-26');
    });
  });

  describe('getWeekEndDate', () => {
    it('should return start of next week when firstDayOfWeek is 0 (Sunday)', () => {
      // Test with Wednesday, March 15, 2025
      const inputDate = new Date(2025, 2, 15); // March 15, 2025 (Wednesday)
      const result = getWeekEndDate(inputDate, 0);
      
      // Expected: Sunday, March 19, 2025 (start of next week)
      expect(formatDateISO(result)).toBe('2025-03-19');
    });

    it('should return start of next week when firstDayOfWeek is 1 (Monday)', () => {
      // Test with Wednesday, March 15, 2025
      const inputDate = new Date(2025, 2, 15); // March 15, 2025 (Wednesday)
      const result = getWeekEndDate(inputDate, 1);
      
      // Expected: Monday, March 20, 2025 (start of next week)
      expect(formatDateISO(result)).toBe('2025-03-20');
    });

    it('should handle month boundaries correctly', () => {
      // Test with last day of month
      const inputDate = new Date(2025, 2, 31); // March 31, 2025 (Friday)
      const result = getWeekEndDate(inputDate, 0); // Sunday start
      
      // Expected: Sunday, April 2, 2025
      expect(formatDateISO(result)).toBe('2025-04-02');
    });

    it('should handle year boundaries correctly', () => {
      // Test with last day of year
      const inputDate = new Date(2025, 11, 31); // December 31, 2025 (Sunday)
      const result = getWeekEndDate(inputDate, 1); // Monday start
      
      // Expected: Monday, January 1, 2025
      expect(formatDateISO(result)).toBe('2025-01-01');
    });
  });

  describe('navigateWeek', () => {
    const testDate = new Date(2025, 2, 15); // March 15, 2025 (Wednesday)

    describe('Forward navigation (direction = 1)', () => {
      it('should navigate to next week with Sunday start', () => {
        const result = navigateWeek(testDate, 1, 0);
        
        // Expected: Sunday, March 19, 2025 (start of next week)
        expect(formatDateISO(result)).toBe('2025-03-19');
      });

      it('should navigate to next week with Monday start', () => {
        const result = navigateWeek(testDate, 1, 1);
        
        // Expected: Monday, March 20, 2025 (start of next week)
        expect(formatDateISO(result)).toBe('2025-03-20');
      });

      it('should navigate to next week with Tuesday start', () => {
        const result = navigateWeek(testDate, 1, 2);
        
        // Expected: Tuesday, March 21, 2025 (start of next week)
        expect(formatDateISO(result)).toBe('2025-03-21');
      });

      it('should handle multiple weeks forward', () => {
        const result = navigateWeek(testDate, 3, 0); // 3 weeks forward
        
        // Expected: Sunday, April 2, 2025
        expect(formatDateISO(result)).toBe('2025-04-02');
      });
    });

    describe('Backward navigation (direction = -1)', () => {
      it('should navigate to previous week with Sunday start', () => {
        const result = navigateWeek(testDate, -1, 0);
        
        // Expected: Sunday, March 5, 2025 (start of previous week)
        expect(formatDateISO(result)).toBe('2025-03-05');
      });

      it('should navigate to previous week with Monday start', () => {
        const result = navigateWeek(testDate, -1, 1);
        
        // Expected: Monday, March 6, 2025 (start of previous week)
        expect(formatDateISO(result)).toBe('2025-03-06');
      });

      it('should navigate to previous week with Tuesday start', () => {
        const result = navigateWeek(testDate, -1, 2);
        
        // Expected: Tuesday, March 7, 2025 (start of previous week)
        expect(formatDateISO(result)).toBe('2025-03-07');
      });

      it('should handle multiple weeks backward', () => {
        const result = navigateWeek(testDate, -3, 0); // 3 weeks backward
        
        // Expected: Sunday, February 26, 2025
        expect(formatDateISO(result)).toBe('2025-02-26');
      });
    });

    describe('Edge cases', () => {
      it('should handle month boundaries when navigating forward', () => {
        const lastDayOfMonth = new Date(2025, 2, 31); // March 31, 2025
        const result = navigateWeek(lastDayOfMonth, 1, 0);
        
        // Should navigate to next week in April
        expect(result.getMonth()).toBe(3); // April
      });

      it('should handle month boundaries when navigating backward', () => {
        const firstDayOfMonth = new Date(2025, 3, 1); // April 1, 2025
        const result = navigateWeek(firstDayOfMonth, -1, 0);
        
        // Should navigate to previous week in March
        expect(result.getMonth()).toBe(2); // March
      });

      it('should handle year boundaries when navigating forward', () => {
        const endOfYear = new Date(2025, 11, 31); // December 31, 2025
        const result = navigateWeek(endOfYear, 1, 0);
        
        // Should navigate to next week in January 2025
        expect(result.getFullYear()).toBe(2025);
        expect(result.getMonth()).toBe(0); // January
      });

      it('should handle year boundaries when navigating backward', () => {
        const startOfYear = new Date(2025, 0, 1); // January 1, 2025
        const result = navigateWeek(startOfYear, -1, 0);
        
        // Should navigate to previous week in December 2025
        expect(result.getFullYear()).toBe(2025);
        expect(result.getMonth()).toBe(11); // December
      });

      it('should handle leap year correctly', () => {
        const leapYearDate = new Date(2025, 1, 29); // February 29, 2025 (leap year)
        const result = navigateWeek(leapYearDate, 1, 0);
        
        // Should navigate to next week in March
        expect(result.getMonth()).toBe(2); // March
      });
    });

    describe('All days of week as firstDayOfWeek', () => {
      const testCases = [
        { firstDay: 0, name: 'Sunday' },
        { firstDay: 1, name: 'Monday' },
        { firstDay: 2, name: 'Tuesday' },
        { firstDay: 3, name: 'Wednesday' },
        { firstDay: 4, name: 'Thursday' },
        { firstDay: 5, name: 'Friday' },
        { firstDay: 6, name: 'Saturday' }
      ];

      testCases.forEach(({ firstDay, name }) => {
        it(`should handle ${name} as first day of week`, () => {
          const result = navigateWeek(testDate, 1, firstDay);
          
          // Verify the result is a valid date
          expect(result).toBeInstanceOf(Date);
          expect(result.getTime()).toBeGreaterThan(testDate.getTime());
        });
      });
    });

    describe('Zero direction (no navigation)', () => {
      it('should return start of current week when direction is 0', () => {
        const result = navigateWeek(testDate, 0, 0);
        
        // Should return start of current week (Sunday)
        expect(formatDateISO(result)).toBe('2025-03-12');
      });

      it('should return start of current week with Monday start when direction is 0', () => {
        const result = navigateWeek(testDate, 0, 1);
        
        // Should return start of current week (Monday)
        expect(formatDateISO(result)).toBe('2025-03-13');
      });
    });
  });

  describe('Integration tests - Week boundaries consistency', () => {
    it('should maintain consistency between getWeekStartDate and navigateWeek', () => {
      const testDate = new Date(2025, 2, 15); // March 15, 2025
      const firstDayOfWeek = 1; // Monday
      
      const weekStart = getWeekStartDate(testDate, firstDayOfWeek);
      const navigatedWeek = navigateWeek(testDate, 0, firstDayOfWeek);
      
      expect(formatDateISO(weekStart)).toBe(formatDateISO(navigatedWeek));
    });

    it('should maintain consistency between getWeekEndDate and navigateWeek', () => {
      const testDate = new Date(2025, 2, 15); // March 15, 2025
      const firstDayOfWeek = 0; // Sunday
      
      const weekEnd = getWeekEndDate(testDate, firstDayOfWeek);
      const nextWeekStart = navigateWeek(testDate, 1, firstDayOfWeek);
      
      expect(formatDateISO(weekEnd)).toBe(formatDateISO(nextWeekStart));
    });

    it('should maintain 7-day intervals when navigating weeks', () => {
      const testDate = new Date(2025, 2, 15); // March 15, 2025
      const firstDayOfWeek = 1; // Monday
      
      const currentWeek = navigateWeek(testDate, 0, firstDayOfWeek);
      const nextWeek = navigateWeek(testDate, 1, firstDayOfWeek);
      const prevWeek = navigateWeek(testDate, -1, firstDayOfWeek);
      
      // Check that intervals are exactly 7 days
      const daysBetweenNext = (nextWeek.getTime() - currentWeek.getTime()) / (1000 * 60 * 60 * 24);
      const daysBetweenPrev = (currentWeek.getTime() - prevWeek.getTime()) / (1000 * 60 * 60 * 24);
      
      expect(daysBetweenNext).toBe(7);
      expect(daysBetweenPrev).toBe(7);
    });
  });
});